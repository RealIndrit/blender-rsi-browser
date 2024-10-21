Blender RSI Browser
====================
Import 3D models from robertsspaceindustries.com into your scene!

Note that CIG still owns the copyright for these models, you probably don't want to be using them commercially, I guess?

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
