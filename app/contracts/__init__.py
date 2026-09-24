"""Pilotage-side copies of the DiddiFree internal contract models.

The canonical producer-side models live in
``backend/app/internal_contracts`` while the protocol settles. These copies
are the consumer side: identical field sets, but tolerant to additive fields
so an upstream module can extend its summary without breaking collection.
Both copies move to ``diddifree-internal-kit`` once the protocol is stable.
"""
