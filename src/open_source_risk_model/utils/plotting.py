# src/open_source_risk_model/utils/plotting.py

from typing import List, Tuple

import matplotlib.pyplot as plt


def plot_piecewise_mapping(
    anchors: List[Tuple[float, float]],
    title: str = "Option A Mapping",
):
    """
    Quick visualization of a piecewise-linear mapping defined by anchors.
    """
    xs: List[float] = []
    ys: List[float] = []

    for (x1, y1), (x2, y2) in zip(anchors, anchors[1:]):
        xs.extend([x1, x2])
        ys.extend([y1, y2])

    plt.figure(figsize=(6, 4))
    plt.plot(xs, ys)
    plt.xlabel("Raw value")
    plt.ylabel("Risk score")
    plt.title(title)
    plt.grid(True)
    return plt
