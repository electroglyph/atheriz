This directory contains the JavaScript for the Atheriz webclient (based on xterm.js).

- `webclient.js` - the main webclient application (connection handling, input,
  map rendering, and the server-to-client WebSocket protocol).
- `xterm.js`, `addon-*.js`, `fontfaceobserver.js` - vendored dependencies.

You can replace or extend these files to customize the client. The server-to-client
message protocol is documented in `docs/12_webclient.md`.
