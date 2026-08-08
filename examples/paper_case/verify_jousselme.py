# -*- coding: utf-8 -*-
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))

from edqsg.evidence import EvidenceFusionEngine

eng = EvidenceFusionEngine((0.2, 0.2, 0.2, 0.2, 0.2), (100, 85, 70, 50, 20))
A = np.array([0.1350, 0.3870, 0.2430, 0.0810, 0.0540, 0.1000])
B = np.array([0.1105, 0.4080, 0.2380, 0.0595, 0.0340, 0.1500])
d = eng._jousselme_distance(A[:5], A[5], B[:5], B[5])
print("论文算例Jousselme距离(代码口径):", round(d, 4))
