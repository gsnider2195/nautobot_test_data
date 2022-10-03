from django.core.management import call_command
from django.db import transaction

from nautobot.dcim.choices import InterfaceTypeChoices
from nautobot.dcim.models import Cable, Device, DeviceRole, DeviceType, Rack, RackGroup, Site
from nautobot.dcim.models.device_component_templates import InterfaceTemplate
from nautobot.dcim.models.devices import Manufacturer
from nautobot.dcim.models.sites import Region
from nautobot.extras.models import Status
from nautobot.utilities.forms.fields import ExpandableNameField


def create_regions():
    regions = {
        "Americas": [
            "Argentina",
            "Brazil",
            "Canada",
            "Chile",
            "Mexico",
            "USA",
        ],
        "APAC": [
            "Australia",
            "Indonesia",
            "Japan",
            "South Korea",
        ],
        "EMEA": [
            "France",
            "Germany",
            "Italy",
            "Spain",
            "United Kingdom",
        ],
    }
    for parent_name, children in regions.items():
        parent = Region.objects.create(name=parent_name)
        for child_name in children:
            Region.objects.create(name=child_name, parent=parent)


def create_sites():
    sites = {
        "Germany": ["Frankfurt Office"],
        "United Kingdom": ["London Office"],
        "USA": [
            "Los Angeles Office",
            "Phoenix Datacenter",
            "St Louis Datacenter",
            "Seattle Office",
        ],
        "Mexico": ["Mexico City Office"],
        "South Korea": ["Seoul Office"],
        "Australia": ["Sydney Office"],
    }
    for region, site_list in sites.items():
        region_obj = Region.objects.get(name=region)
        for site in site_list:
            Site.objects.create(name=site, region=region_obj)


def create_manufacturers():
    manufacturers = [
        "Arista",
        "Aruba",
        "Brocade",
        "Checkpoint",
        "Cisco",
        "Juniper",
        "Palo Alto",
    ]
    for manufacturer in manufacturers:
        Manufacturer.objects.create(name=manufacturer)


def create_device_roles():
    roles = [
        "Access switch",
        "CE router",
        "Core switch",
        "Distribution switch",
        "End of row switch",
        "Firewall",
        "Top of rack switch",
    ]
    for role in roles:
        DeviceRole.objects.create(name=role, vm_role=False)


def create_device_types():
    cisco = Manufacturer.objects.get(name="Cisco")
    device_types = [
        {
            "manufacturer": cisco,
            "model": "C2921",
            "u_height": 2,
            "is_full_depth": False,
        },
        {
            "manufacturer": cisco,
            "model": "C9300L-48T-4X",
            "is_full_depth": False,
        },
        {
            "manufacturer": cisco,
            "model": "Nexus 3232C",
        },
        {
            "manufacturer": cisco,
            "model": "Nexus 9332C",
        },
        {
            "manufacturer": cisco,
            "model": "Nexus 9508",
            "u_height": 13,
        },
    ]

    for dt in device_types:
        DeviceType.objects.create(**dt)

    interfaces = [
        {
            "device_type": DeviceType.objects.get(model="C2921"),
            "type": InterfaceTypeChoices.TYPE_1GE_FIXED,
            "name": "GigabitEthernet[0-2]",
        },
        {
            "device_type": DeviceType.objects.get(model="C9300L-48T-4X"),
            "type": InterfaceTypeChoices.TYPE_1GE_FIXED,
            "name": "GigabitEthernet1/0/[1-48]",
        },
        {
            "device_type": DeviceType.objects.get(model="C9300L-48T-4X"),
            "type": InterfaceTypeChoices.TYPE_10GE_FIXED,
            "name": "TengigabitEthernet1/1/[1-4]",
        },
        {
            "device_type": DeviceType.objects.get(model="Nexus 3232C"),
            "type": InterfaceTypeChoices.TYPE_100GE_QSFP28,
            "name": "Ethernet[1-32]",
        },
        {
            "device_type": DeviceType.objects.get(model="Nexus 9332C"),
            "type": InterfaceTypeChoices.TYPE_100GE_QSFP28,
            "name": "Ethernet[1-32]",
        },
        {
            "device_type": DeviceType.objects.get(model="Nexus 9508"),
            "type": InterfaceTypeChoices.TYPE_100GE_QSFP28,
            "name": "Ethernet1/[1-8]/[1-32]",
        },
    ]

    e = ExpandableNameField()
    for interface in interfaces:
        for int in e.to_python(interface["name"]):
            interface["name"] = int
            InterfaceTemplate.objects.create(**interface)


def create_rack_groups():
    rack_groups = [
        {"dc_name": "PHX", "site": "Phoenix Datacenter"},
        {"dc_name": "STL", "site": "St Louis Datacenter"},
    ]
    for dc in rack_groups:
        site = Site.objects.get(name=dc["site"])
        parent = RackGroup.objects.create(name=f"{dc['dc_name']} Datacenter Racks (ALL)", site=site)
        for row in range(1, 9):
            RackGroup.objects.create(name=f"{dc['dc_name']} Row {row}", parent=parent, site=site)


def create_racks():
    for rack_group in RackGroup.objects.filter(parent__isnull=False):
        dc_name, _, row = rack_group.name.split(" ")
        for rack_num in range(1, 9):
            Rack.objects.create(
                name=f"{dc_name} {row}-{rack_num}",
                group=rack_group,
                site=rack_group.site,
            )


def connect_tor_to_eor(eor, tor, starting_interface):
    status_connected = Status.objects.get_for_model(Cable).get(slug="connected")
    int1 = tor.interfaces.get(name="Ethernet1")
    int2 = tor.interfaces.get(name="Ethernet2")
    inteor1 = eor.interfaces.get(name=f"Ethernet{starting_interface}")
    inteor2 = eor.interfaces.get(name=f"Ethernet{starting_interface+1}")
    Cable.objects.create(
        termination_a=int1,
        termination_b=inteor1,
        status=status_connected,
    )
    Cable.objects.create(
        termination_a=int2,
        termination_b=inteor2,
        status=status_connected,
    )


def create_switches():

    active = Status.objects.get_for_model(Rack).get(slug="active")
    roleeor = DeviceRole.objects.get(slug="end-of-row-switch")
    roletor = DeviceRole.objects.get(slug="top-of-rack-switch")
    typeeor = DeviceType.objects.get(slug="nexus-9332c")
    typetor = DeviceType.objects.get(slug="nexus-3232c")
    sitephx = Site.objects.get(slug="phoenix-datacenter")
    sitestl = Site.objects.get(slug="st-louis-datacenter")

    for dc_name, dc in {"PHX": sitephx, "STL": sitestl}.items():
        for row in range(1, 9):
            eorswitch = Device.objects.create(
                name=f"{dc_name.lower()}-spn{row}",
                device_role=roleeor,
                device_type=typeeor,
                site=dc,
                rack=Rack.objects.get(name=f"{dc_name} {row}-1"),
                position=42,
                face="front",
                status=active,
            )
            for rack in range(1, 9):
                torswitch1 = Device.objects.create(
                    name=f"{dc_name.lower()}-leaf{row}-{rack}-1",
                    device_role=roletor,
                    device_type=typetor,
                    site=dc,
                    rack=Rack.objects.get(name=f"{dc_name} {row}-{rack}"),
                    position=41,
                    face="front",
                    status=active,
                )
                connect_tor_to_eor(eor=eorswitch, tor=torswitch1, starting_interface=rack * 2 - 1)
                torswitch2 = Device.objects.create(
                    name=f"{dc_name.lower()}-leaf{row}-{rack}-2",
                    device_role=roletor,
                    device_type=typetor,
                    site=dc,
                    rack=Rack.objects.get(name=f"{dc_name} {row}-{rack}"),
                    position=40,
                    face="front",
                    status=active,
                )
                connect_tor_to_eor(eor=eorswitch, tor=torswitch2, starting_interface=rack * 2 + 15)


def clear():
    Cable.objects.all().delete()
    Device.objects.all().delete()
    Rack.objects.all().delete()
    RackGroup.objects.all().delete()
    DeviceType.objects.all().delete()
    DeviceRole.objects.all().delete()
    Manufacturer.objects.all().delete()
    Site.objects.all().delete()
    Region.objects.all().delete()


def create():

    with transaction.atomic():
        create_regions()  # 18 regions
        create_sites()  # 9 sites
        create_manufacturers()  # 7 manufacturers
        create_device_roles()  # 7 device roles
        create_device_types()  # 5 device types
        create_rack_groups()  # 18 rack groups
        create_racks()  # 128 racks
        create_switches()  # 272 devices, 512 cables, 8704 interfaces

        # dump data
        call_command(
            "dumpdata",
            "--natural-foreign",
            "--natural-primary",
            "--exclude",
            "django_rq",
            "--exclude",
            "extras.job",
            "--exclude",
            "extras.customfield",
            "--exclude",
            "contenttypes",
            "--exclude",
            "auth.permission",
            "--traceback",
            "--indent",
            "4",
            "--output",
            "db_output_test.json",
            "--format",
            "json",
        )

        transaction.set_rollback(True)
