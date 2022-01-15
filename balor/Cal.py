import numpy as np
import scipy
import scipy.interpolate
import gc
from . import RBFInterpolator

from functools import lru_cache
MAX_CACHE = 2048

class Cal:
    def __init__(self, cal_file):
        self.enabled = False

        if cal_file is None:
            self.enabled = False
            return

        if cal_file is not None:
            try:
                calfile = [h.split() for h in open(cal_file, "r").readlines()]
            except (IOError, OSError):
                print("Calibration file could not be loaded.")
                return

        self.cache = {}
        self.enabled = True
        mcal = np.asarray([(float(h[0]), float(h[1])) for h in calfile])
        gcal = np.asarray([(int(h[4],16), int(h[5],16)) for h in calfile])

        mm_x, mm_y, g_x, g_y = mcal[:,0], mcal[:,1], gcal[:,0], gcal[:,1]

        self.mm_xmax = mm_x[-1]
        self.mm_xmin = mm_x[0]
        self.mm_ymax = mm_y[-1]
        self.mm_ymin = mm_y[0]

        self.linear_x = (mm_x[49] - mm_x[31]) / (g_x[49] - g_x[31])
        self.linear_y = (mm_y[41] - mm_y[39]) / (g_y[41] - g_y[39])

        #self.interpolator = scipy.interpolate.LinearNDInterpolator(
        #        mcal,
        #        gcal,
        #        )
        self.interpolator = RBFInterpolator.RBFInterpolator(
                mcal,
                gcal,
                )

        #self.interpolator = scipy.interpolate.CloughTocher2DInterpolator(
        #        mcal,
        #        gcal,
        #        )
    @lru_cache(maxsize=MAX_CACHE)
    def interpolate(self, x, y):
        if self.enabled:
            rv = self.interpolator([(y, x)])[0]
            return int(round(rv[1])), int(round(rv[0]))
        else:
            # A disabled cal file interpolates 1 to 1 with bound range checks.
            return int(round(x)), int(round(y))

    #def interpolate_list(self, xys):
        #rv =  self.interpolator(xys)
        #return [(int(round(x)), int(round(y))) for x,y in rv]



        
