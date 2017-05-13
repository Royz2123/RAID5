# RAID5

A final project for the Gvahim program. This project offers a system that can store your data on multiple servers, and back them up based on the RAID5 protocol (Redundant Array of Independent Disks). The system lets you manage your servers, and works perfectly even with one faulty block device.

## Getting Started

These instructions will get you a copy of the project up and running on your local machine for development and testing purposes.

### Prerequisites

Here are the things you will need to download in order to get this system up and running:

```
1) Download and Install Python2.7
2) Download this repository on your machine (Windows coming soon)
3) Download and Install Mozilla Firefox (currently buggy on Chrome)
```

### Execution

Running the servers can be done as follows:

WINDOWS & LINUX ALIKE:
Reach parent directory (RAID5)
''
cd [location of RAID5]
''
Running Frontend Server:
''
python -m frontend [args]
''
Running Block Device Server:
''
python -m block_device [args]
''

Testing the servers can be done from any browser (Firefox currently recommended)

### Arguments

In both the Frontend and the Block Devices, the configuration file needs to be specified as args. The Block Devices also require a bind port as shown below:
''
python -m frontend --config-file frontend/config.ini
python -m block_device --config-file block_device/disks/config0.ini --bind-port 8090
python -m block_device --config-file block_device/disks/config1.ini --bind-port 8091
''
Note: All other Arguments are optional, see --help for help
Note: The configuration files can be created from scratch by a python script from the parent directory (RAID5):
''
python config_disks.py <NUM_OF_BLOCK_DEVICES>
''
Note: UUID's can be changed manually from the configuration files


## Authors

* **Roy Zohar** - *Initial work* - [PurpleBooth](https://github.com/PurpleBooth)

See also the list of [contributors](https://github.com/Royz2123/RAID5/contributors) who participated in this project.


## Acknowledgments

* A huge thanks to Alon and Sarit for all the support
