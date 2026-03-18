# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for NetForge — single-file Windows executable."""

import os

block_cipher = None
root = os.path.abspath('.')

a = Analysis(
    ['NetForge.py'],
    pathex=[root],
    binaries=[],
    datas=[
        (os.path.join(root, 'data'), 'data'),
        (os.path.join(root, 'NetForge.ico'), '.'),
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
    a.binaries,
    a.datas,
    [],
    name='NetForge',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    console=False,
    icon='NetForge.ico',
)
