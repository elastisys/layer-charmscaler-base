# work-around until fix is released in charms.reactive
# import reactive.X instead of relative imports
import os.path
from pkgutil import extend_path
import sys


charm_dir = os.path.abspath(os.path.join(os.path.dirname(__file__),
                                         os.pardir, os.pardir))
if charm_dir not in sys.path:
    sys.path.append(charm_dir)

__path__ = extend_path(__path__, __name__)
