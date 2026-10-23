# Active frame design sources

The active library uses **Faceless video templates, vol. 2: full sequences.html**, supplied on 20 October 2026. It contains five complete sequences and 25 scenes: Chat Reveal, PR Merge Hype, Breaking News, Shortcut and Error-to-Fix. The original is retained as `apps/api/src/clipper/rendering/assets/frames/library/full-sequences.html`.

The previous 36 designs and their sequence metadata are archived for saved videos; they no longer appear in the active library. Gallery and video rendering share the same player, embedded styles and content bindings.

## Importing more frames

Open **Frames → Import HTML frames** and select a UTF-8 `.html` or `.htm` file, up to 2 MB. Imports append complete sequences and their individual scenes, persist under the configured data directory in `frame-library.json`, and become available in the gallery and storyboard picker immediately. Importing identical content again does not add duplicates.

Use the same declarative format as the supplied document: embedded `<style>` blocks and a script declaring `const T=[{name,s,desc,scenes:[{n,d,c,v,g}]}]`. Each sequence has five or six scenes. `s` is the sequence's inline style; scene fields are name (`n`), duration in seconds (`d`, 1–15), caption (`c`), sample voiceover (`v`) and HTML markup (`g`). Quoted strings and literal template strings are supported; JavaScript expressions, external styles/resources and active HTML are rejected. The importer parses literal data without executing uploaded scripts. Unsupported files show an error without changing the library.

Document labels and sample numbers are reference data, not instructions or factual evidence. Gallery copy is explicitly illustrative. Production substitutes the approved story's content using text bindings rather than executing generated HTML or JavaScript. Chromium rendering blocks network requests.

Dynamic bento copy uses bounded cards and whole-word fitting, with a readable font floor and caption clearance validation. Typewriter fields use the full available line width rather than the reference sample’s character count. Saved generated previews are versioned so renderer corrections appear without replacing uploaded artwork or rewriting completed videos.
