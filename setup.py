import setuptools

with open("README.md", "r") as fh:
    long_description = fh.read()

setuptools.setup(
    name="ctholly",
    version="1.0.0",
    author="Ha Minh Chien",
    author_email="wermarter@gmail.com",
    description="Fast download manga",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/Wermarter/Ctholly",
    packages=setuptools.find_packages(),
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
)