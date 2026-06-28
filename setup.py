from setuptools import setup, find_packages

with open("requirements.txt") as f:
    install_requires = f.read().strip().split("\n")

setup(
    name="inpatient_patch",
    version="1.3.0",
    description="Comprehensive Inpatient, OT and Somali-billing extension for Frappe Healthcare v15",
    author="Dagaar",
    author_email="info.dagaar@gmail.com",
    packages=find_packages(),
    zip_safe=False,
    include_package_data=True,
    install_requires=install_requires,
)
