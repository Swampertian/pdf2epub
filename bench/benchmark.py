#!/usr/bin/env python3
"""
Baseline benchmark for the pdf2epub pipeline.

Measures each phase separately so we know where time and memory actually go:
  import        - importing marker/torch
  load_models   - loading surya/marker models (to GPU if available)
  convert       - marker PDF -> markdown (layout, OCR, tables, ...)
  save          - writing markdown, metadata and images
  epub          - markdown -> EPUB (non-interactive, defaults for metadata)

For every phase it records wall time, process CPU time, average CPU
utilisation, peak RSS, peak GPU memory used by this process and average GPU
utilisation (sampled every --interval seconds).

Usage:
  python bench/benchmark.py book.pdf --pages 20 --json results.json
"""
import argparse
import json
import os
import platform
import sys
import threading
import time
from contextlib import contextmanager
from pathlib import Path

import psutil

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

try:
    import pynvml
    pynvml.nvmlInit()
    _GPU = pynvml.nvmlDeviceGetHandleByIndex(0)
except Exception:
    _GPU = None


class Sampler(threading.Thread):
    """Samples RSS, CPU and GPU usage of this process in the background."""

    def __init__(self, interval: float):
        super().__init__(daemon=True)
        self.interval = interval
        self.proc = psutil.Process()
        self.proc.cpu_percent(None)
        self._halt = threading.Event()
        self.reset()

    def reset(self):
        self.samples = []

    def _gpu_sample(self):
        if _GPU is None:
            return 0, 0
        util = pynvml.nvmlDeviceGetUtilizationRates(_GPU).gpu
        mem = 0
        for p in pynvml.nvmlDeviceGetComputeRunningProcesses(_GPU):
            if p.pid == self.proc.pid and p.usedGpuMemory:
                mem += p.usedGpuMemory
        return util, mem

    def run(self):
        while not self._halt.wait(self.interval):
            try:
                rss = self.proc.memory_info().rss
                cpu = self.proc.cpu_percent(None)
                gpu_util, gpu_mem = self._gpu_sample()
                self.samples.append((rss, cpu, gpu_util, gpu_mem))
            except Exception:
                pass

    def stop(self):
        self._halt.set()


def _mb(b):
    return round(b / 2**20, 1)


class Bench:
    def __init__(self, interval):
        self.sampler = Sampler(interval)
        self.sampler.start()
        self.phases = {}

    @contextmanager
    def phase(self, name):
        proc = self.sampler.proc
        self.sampler.reset()
        t0 = time.perf_counter()
        c0 = proc.cpu_times()
        rss0 = proc.memory_info().rss
        try:
            import torch
            if torch.cuda.is_available():
                torch.cuda.reset_peak_memory_stats()
        except Exception:
            pass
        yield
        wall = time.perf_counter() - t0
        c1 = proc.cpu_times()
        cpu_s = (c1.user - c0.user) + (c1.system - c0.system)
        s = self.sampler.samples or [(proc.memory_info().rss, 0, 0, 0)]
        rec = {
            "wall_s": round(wall, 3),
            "cpu_s": round(cpu_s, 3),
            "cpu_avg_pct": round(100 * cpu_s / wall, 1) if wall else 0,
            "rss_start_mb": _mb(rss0),
            "rss_peak_mb": _mb(max(x[0] for x in s)),
            "gpu_util_avg_pct": round(sum(x[2] for x in s) / len(s), 1),
            "gpu_mem_peak_mb": _mb(max(x[3] for x in s)),
        }
        try:
            import torch
            if torch.cuda.is_available():
                rec["torch_alloc_peak_mb"] = _mb(torch.cuda.max_memory_allocated())
        except Exception:
            pass
        self.phases[name] = rec
        print(f"  {name:<12} {rec['wall_s']:>8.2f}s  cpu {rec['cpu_avg_pct']:>6.1f}%  "
              f"rss {rec['rss_peak_mb']:>8.1f}MB  gpu {rec['gpu_util_avg_pct']:>5.1f}%  "
              f"vram {rec['gpu_mem_peak_mb']:>7.1f}MB", flush=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pdf", type=Path)
    ap.add_argument("--pages", type=int, default=None, help="number of pages (default: all)")
    ap.add_argument("--start", type=int, default=0, help="first page index")
    ap.add_argument("--out", type=Path, default=None, help="output dir (default: bench/out/<stem>)")
    ap.add_argument("--json", type=Path, default=None, help="write results to this JSON file")
    ap.add_argument("--interval", type=float, default=0.2, help="sampling interval in seconds")
    args = ap.parse_args()

    out = args.out or Path(__file__).parent / "out" / args.pdf.stem
    out.mkdir(parents=True, exist_ok=True)
    bench = Bench(args.interval)

    import pypdfium2
    total_pages = len(pypdfium2.PdfDocument(str(args.pdf)))
    n_pages = min(args.pages or total_pages, total_pages - args.start)
    print(f"PDF: {args.pdf.name}  pages: {n_pages}/{total_pages} (start {args.start})")

    with bench.phase("import"):
        import torch
        import marker.converters.pdf  # noqa: F401  (measure heavy imports here)
        from pdf2epub import epub, extraction, workspace
        from pdf2epub.metadata import BookDescription

    with bench.phase("load_models"):
        models = extraction.load_models()

    pages = list(range(args.start, args.start + n_pages))
    with bench.phase("convert"):
        rendered = extraction.extract_pdf(args.pdf, models, pages)

    with bench.phase("save"):
        workspace.save_extraction(rendered, out, args.pdf.stem)

    epub_path = out / f"{args.pdf.stem}.epub"
    with bench.phase("epub"):
        epub.build_epub(out, epub_path, BookDescription.for_workspace(out))

    bench.sampler.stop()
    conv = bench.phases["convert"]["wall_s"]
    result = {
        "pdf": args.pdf.name,
        "pages": n_pages,
        "pages_per_s": round(n_pages / conv, 3) if conv else None,
        "s_per_page": round(conv / n_pages, 3) if n_pages else None,
        "markdown_chars": len(rendered.markdown),
        "images": len(rendered.images or {}),
        "epub_bytes": epub_path.stat().st_size if epub_path.exists() else None,
        "phases": bench.phases,
        "env": {
            "python": platform.python_version(),
            "torch": torch.__version__,
            "device": torch.cuda.get_device_name(0) if torch.cuda.is_available() else "cpu",
            "cpus": os.cpu_count(),
            "TORCH_DEVICE": os.environ.get("TORCH_DEVICE"),
        },
    }
    print(f"\nconvert: {result['pages_per_s']} pages/s  ({result['s_per_page']} s/page)")
    
    if args.json:
        out.write_text(json.dumps(result, indent=2))
        print(f"results: {args.json}")


if __name__ == "__main__":
    main()
