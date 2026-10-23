# The bundled label reader

`index.min.js` is `umd/index.min.js` from the npm package `@zxing/library`
version 0.20.0, unchanged: the same file the stock app has served as its
`zxing.min.js` since July 2026, so a phone reads shelf labels in Reactor
exactly as it does there.

- sha256 of `index.min.js`: `a560a87011ff742441d5770cc5ab0f64cfbfb7b228966c5433783e3ba96dd410`
- npm integrity of the package: `sha512-6Ev6rcqVjMakZFIDvbUf0dtpPGeZMTfyxYg4HkVWioWeN7cRcnUWT3bU6sdohc82O1nPXcjq6WiGfXX2Pnit6A==`
- Licence: `LICENSE` beside it, as shipped in the package (Apache 2.0; the
  package's own `package.json` says MIT).

Reactor serves it at `/assets/reader.js?v=<hash>` (`gizmo/rendering.py`).
The page never loads it up front: the shell only names its URL in
`<meta name="label-reader">`, and the camera loads it when a phone's browser
has no barcode reader of its own. A test checks the served bytes against the
sha256 above, so a changed file cannot slip in unnoticed.

To change version: take `umd/index.min.js` and `LICENSE` from the new
package, check its integrity against the registry, and update both lines
above.
