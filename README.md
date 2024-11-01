Blender RSI Browser
====================
Import 3D models from robertsspaceindustries.com into your scene!

Plugin requires [Import OpenCTM (.ctm)](https://github.com/RealIndrit/blender-import-openctm) plugin.
Note that CIG still owns the copyright for these models, you probably don't want to be using them commercially. I do
in no way endorse using this outside strictly personal and educational use. Any legal issues is on you as the user.

Dev notes
---------
Blender 4.2.0 uses python 3.11 specifically, so use that to install bpy and create a virtualenv for if you want to have IDE autocompletions and such:
```
python3.11 -m venv venv
venv/bin/pip install bpy blender-stubs
```

Build the addon .zip file:
```
blender --command extension build
```

install:
* blender -> edit -> preferences -> add-ons -> install from disk -> select the .zip file


Credits
-------
This plugin was heavily inspired by [Ikea Browser](https://github.com/shish/blender-ikea-browser/), go check it out!