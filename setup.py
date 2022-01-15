from setuptools import setup
setup(
    install_requires=[
        "scipy"
    ],
    entry_points={
        'meerk40t.plugins': [
            'Balor=balormk.main:plugin',
            'BalorGui=balormk.gui.gui:plugin',
        ],
    },
)