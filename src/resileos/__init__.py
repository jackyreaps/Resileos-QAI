"""
Resileos-QAI.

Hybrid Classical Residual Core + HDRIFT Generative Substrate.

Subpackages:
    resileos.substrate     — QD-TER two-head system, phasor graph,
                             CSI, agency (see docs/300-substrate/)
    resileos.integration   — HTTP clients for external services

Top-level re-exports are intentionally not provided. Import from the
subpackage you need:

    from resileos.core import ResidualCore
    from resileos.substrate import PhasorGraph, AgencyGroup, CSIState

The historical pattern of re-exporting geometry/reduction at the
package root was removed: those modules live under `resileos.substrate`,
not at the root, and importing them from the root broke `import resileos`.
"""

__version__ = "1.0.0"

__all__ = ["__version__"]
