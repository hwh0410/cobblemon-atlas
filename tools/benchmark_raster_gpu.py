#!/usr/bin/env python3
"""CPU NumPy vs CUDA Torch raster-math microbenchmark, NOT an end-to-end renderer.

Compares the same triangle barycentric, depth and UV math on synthetic geometry.
No WebP encoding, bone transforms, textures or compositing are included.
"""
import argparse
import json
import time

import numpy as np


def geometry(triangles, size, seed=13):
    rng = np.random.default_rng(seed)
    points = rng.uniform(0, size, (triangles, 3, 2)).astype("float32")
    uv = rng.uniform(0, 1, (triangles, 3, 2)).astype("float32")
    z = rng.uniform(0, 1, (triangles, 3)).astype("float32")
    return points, uv, z


def numpy_raster_math(points, uv, z, size):
    coords = np.arange(size, dtype="float32") + .5
    yy, xx = np.meshgrid(coords, coords, indexing="ij")
    x, y = xx[None], yy[None]
    x0, x1, x2 = [points[:, i, 0, None, None] for i in range(3)]
    y0, y1, y2 = [points[:, i, 1, None, None] for i in range(3)]
    den = (y1-y2)*(x0-x2)+(x2-x1)*(y0-y2)
    den = np.where(np.abs(den) < 1e-8, 1e-8, den)
    w0 = ((y1-y2)*(x-x2)+(x2-x1)*(y-y2))/den
    w1 = ((y2-y0)*(x-x2)+(x0-x2)*(y-y2))/den
    w2 = 1-w0-w1
    inside = (w0 >= 0)&(w1 >= 0)&(w2 >= 0)
    depth = w0*z[:,0,None,None]+w1*z[:,1,None,None]+w2*z[:,2,None,None]
    u = w0*uv[:,0,0,None,None]+w1*uv[:,1,0,None,None]+w2*uv[:,2,0,None,None]
    return float(np.sum(np.where(inside, depth+u, 0), dtype=np.float64)), int(inside.sum())


def torch_raster_math(torch, points, uv, z, size):
    coords = torch.arange(size, dtype=torch.float32, device=points.device)+.5
    y, x = torch.meshgrid(coords, coords, indexing="ij")
    x, y = x[None], y[None]
    x0, x1, x2 = [points[:,i,0,None,None] for i in range(3)]
    y0, y1, y2 = [points[:,i,1,None,None] for i in range(3)]
    den = (y1-y2)*(x0-x2)+(x2-x1)*(y0-y2)
    den = torch.where(torch.abs(den)<1e-8, torch.full_like(den,1e-8), den)
    w0 = ((y1-y2)*(x-x2)+(x2-x1)*(y-y2))/den
    w1 = ((y2-y0)*(x-x2)+(x0-x2)*(y-y2))/den
    w2 = 1-w0-w1
    inside = (w0>=0)&(w1>=0)&(w2>=0)
    depth = w0*z[:,0,None,None]+w1*z[:,1,None,None]+w2*z[:,2,None,None]
    u = w0*uv[:,0,0,None,None]+w1*uv[:,1,0,None,None]+w2*uv[:,2,0,None,None]
    result = torch.where(inside,depth+u,torch.zeros_like(depth))
    return result.sum(), inside.sum()


def benchmark(triangles=32, size=224, repeats=5):
    points, uv, z = geometry(triangles, size)
    result = dict(benchmark="barycentric_depth_uv_only", triangles=triangles,
                  size=size, repeats=repeats, not_end_to_end=True)
    numpy_raster_math(points, uv, z, size)
    t0 = time.perf_counter()
    baseline = None
    for _ in range(repeats):
        baseline = numpy_raster_math(points, uv, z, size)
    result["cpu_numpy_ms"] = round((time.perf_counter()-t0)*1000/repeats, 3)
    result["cpu_result"] = dict(sum=round(baseline[0],2), coverage=baseline[1])
    try:
        import torch
    except ImportError:
        result["gpu_status"] = "torch_not_installed"
        return result
    if not torch.cuda.is_available():
        result["gpu_status"] = "cuda_unavailable"
        return result
    device = "cuda"
    result["gpu_name"] = torch.cuda.get_device_name(0)
    p, u, d = [torch.tensor(x,device=device) for x in (points,uv,z)]
    for _ in range(2):
        torch_raster_math(torch,p,u,d,size)
    torch.cuda.synchronize()
    t0=time.perf_counter()
    for _ in range(repeats):
        gpu_sum,gpu_coverage=torch_raster_math(torch,p,u,d,size)
    torch.cuda.synchronize()
    result["gpu_compute_ms"] = round((time.perf_counter()-t0)*1000/repeats,3)
    t0=time.perf_counter()
    for _ in range(repeats):
        p1,u1,d1=[torch.tensor(x,device=device) for x in (points,uv,z)]
        gpu_sum,gpu_coverage=torch_raster_math(torch,p1,u1,d1,size)
        gpu_sum.item();gpu_coverage.item()
    torch.cuda.synchronize()
    result["gpu_with_transfer_ms"] = round((time.perf_counter()-t0)*1000/repeats,3)
    result["gpu_result"] = dict(sum=round(float(gpu_sum.item()),2),coverage=int(gpu_coverage.item()))
    result["coverage_equal"] = result["gpu_result"]["coverage"] == baseline[1]
    result["relative_sum_error"] = round(abs(float(gpu_sum.item())-baseline[0])/max(abs(baseline[0]),1),6)
    result["gpu_status"] = "measured"
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--triangles",type=int,default=32)
    p.add_argument("--size",type=int,default=224)
    p.add_argument("--repeats",type=int,default=5)
    p.add_argument("--output")
    args=p.parse_args()
    if not (1<=args.triangles<=128 and 64<=args.size<=512 and 1<=args.repeats<=100):
        p.error("unsafe benchmark dimensions")
    result=benchmark(args.triangles,args.size,args.repeats)
    print(json.dumps(result,ensure_ascii=False,indent=2))
    if args.output:
        from pathlib import Path
        Path(args.output).parent.mkdir(parents=True,exist_ok=True)
        Path(args.output).write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n")


if __name__=="__main__":
    main()
