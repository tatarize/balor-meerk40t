from setuptools import setup
setup(
    install_requires=[
        "scipy"
    ],
    entry_points={
        'meerk40t.plugin': [
            'Balor=balormk.main:plugin',
        ],
    },
)