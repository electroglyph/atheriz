This is just a little unicode drawing app which will become the basis for my map designer in [AtheriZ](https://github.com/electroglyph/atheriz)

diagonal line drawing is a bit janky, but i can't be arsed to fix it right now

probably still a few other bugs to work out

`npm run build` to build, and `npm run dev` to run it locally.

The build also includes the TypeScript AtheriZ webclient at `dist/webclient/`.

To stage the compiled assets into the Python package, run:

`python deploy.py package`

(equivalently `npm run deploy:package`). The script builds first; pass
`--no-build` to stage an existing `dist/`.

To deploy into a game web directory, run:

`python deploy.py game --web-root /path/to/game/web`

note: this is almost entirely AI generated code, though i've attempted to do it sanely
