import deckyPlugin from "@decky/rollup";

// The Decky preset does the whole build: bundles src/index.tsx to
// dist/index.js, externalises react and @decky/*, and emits the shape the
// loader expects. There is nothing project-specific to add.
//
// It is the package's *default* export, not a named `defineConfig`. Importing
// the latter is a SyntaxError raised before rollup starts, which is what this
// file did until someone tried to build it.
export default deckyPlugin();
