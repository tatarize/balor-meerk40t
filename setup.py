from setuptools import setup
setup(
    install_requires=[
        "scipy"
    ],
    entry_points={
        'meerk40t.plugins': [
            'Balor=balor.main:plugin',
            'BalorGui=balor.gui.gui:plugin',
        ],
    },
)