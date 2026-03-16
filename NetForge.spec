# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for NetForge — single-folder Windows executable."""

import os

block_cipher = None
root = os.path.abspath('.')

a = Analysis(
    ['NetForge.py'],
    pathex=[root],
    binaries=[],
    datas=[
        (os.path.join(root, 'data'), 'data'),
    ],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['unittest', 'pydoc', 'doctest'],
    noarchive=False,
    cipher=block_cipher,
)

pyz = PYZ(a.pure, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='NetForge',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,          # no terminal window — GUI only
    icon='NetForge.ico',
    contents_directory='.',  # keep data/ next to the exe (no _internal)
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='NetForge',
)
