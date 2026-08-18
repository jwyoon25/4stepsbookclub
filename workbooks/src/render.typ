#import "../system/renderer.typ": render-bundle

#let data-path = sys.inputs.at("data", default: none)
#if data-path == none {
  panic("Missing --input data=/path/to/normalized-build.json")
}

#let build-data = json(data-path)

#render-bundle(build-data)
