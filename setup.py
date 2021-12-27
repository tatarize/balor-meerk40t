from setuptools import setup
setup(
    install_requires=[
        "meerk40t>=0.8.0-beta1",
    ],
    entry_points={
        'meerk40t.plugins': [
            'Balor=balor.main:plugin',
            'BalorGui=balor.gui.gui:plugin',
        ],
    },
)