"""CPU prototype for a studio codec built on ResidualCore's residual stack.

The control packet (RES-201) is unchanged. ``codec.py`` is a side packet
that stores every layer's bipolar factors and its least-squares scale so
a decode can rebuild the approximation.
"""
