"""Per-feature HTTP route modules.

Each module exposes free functions ``h_*(handler, parsed[, body])``
that the dispatch tables in :class:`lib.server.Handler` reference
directly. Splitting by feature group keeps :mod:`lib.server` from
absorbing every new route's full body.

The shape mirrors :mod:`lib.tb_cmds`, which already groups the
``tb`` CLI verbs the same way.
"""
