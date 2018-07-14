#!/usr/bin/python

#
# Copyright (c) 2018 Juniper Networks, Inc. All rights reserved.
#

"""
This file contains base class to support tests for all major workflows
supported by fabric ansible
"""
import logging
import pprint
import time
import sys
import requests

from cfgm_common.exceptions import (
    RefsExistError,
    NoIdError
)
from vnc_api.vnc_api import VncApi
from vnc_api.gen.resource_client import Fabric
from vnc_api.gen.resource_client import FabricNamespace
from vnc_api.gen.resource_client import DeviceImage


# pylint: disable=E1101
class SanityBase(object):
    """Base class for fabric ansible sanity tests"""

    @staticmethod
    def _init_logging(cfg, name):
        logger = logging.getLogger('sanity_test')
        logger.setLevel(cfg['level'])

        file_handler = logging.FileHandler(
            '%s/fabric_ansibile_%s.log' % (cfg['file']['dir'], name), mode='w')
        file_handler.setLevel(cfg['file']['level'])
        console_handler = logging.StreamHandler()
        console_handler.setLevel(cfg['console'])

        formatter = logging.Formatter(
            '%(asctime)s %(levelname)-8s %(message)s',
            datefmt='%Y/%m/%d %H:%M:%S')
        file_handler.setFormatter(formatter)
        console_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
        logger.addHandler(console_handler)

        return logger
    # end _init_logging

    def test(self):
        """Override this method in the derived class"""
        pass

    def __init__(self, cfg, name):
        if cfg is None:
            raise KeyError("Missing required args: cfg")
        if name is None:
            raise KeyError("Missing required args: name")

        self._name = name
        self._timeout = cfg['wait_for_job']['timeout']
        self._max_retries = cfg['wait_for_job']['max_retries']
        self._logger = SanityBase._init_logging(cfg['log'], name)
        self._api_server = cfg['api_server']
        self._analytics = cfg['analytics']
        self._api = VncApi(
            api_server_host=self._api_server['host'],
            api_server_port=self._api_server['port'],
            username=self._api_server['username'],
            password=self._api_server['password'],
            tenant_name=self._api_server['tenant'])
    # end __init__

    def create_fabric(self, fab_name, prouter_passwords):
        """create fabric with list of device passwords"""
        self._logger.info('Creating fabric: %s', fab_name)
        fq_name = ['default-global-system-config', fab_name]
        fab = Fabric(
            name=fab_name,
            fq_name=fq_name,
            parent_type='global-system-config',
            fabric_credentials={
                'device_credential': [{
                    'credential': {
                        'username': 'root', 'password': passwd
                    },
                    'vendor': 'Juniper',
                    'device_family': None
                } for passwd in prouter_passwords]
            }
        )
        try:
            fab_uuid = self._api.fabric_create(fab)
            fab = self._api.fabric_read(id=fab_uuid)
        except RefsExistError:
            self._logger.warn("Fabric '%s' already exists", fab_name)
            fab = self._api.fabric_read(fq_name=fq_name)

        self._logger.debug(
            "Fabric created:\n%s",
            pprint.pformat(self._api.obj_to_dict(fab), indent=4))
        return fab
    # end _create_fabric

    def add_mgmt_ip_namespace(self, fab, name, cidrs):
        """add management ip prefixes as fabric namespace"""
        ns_name = 'mgmt_ip-' + name
        self._logger.info(
            'Adding management ip namespace "%s" to fabric "%s" ...',
            ns_name, fab.name)

        subnets = []
        for cidr in cidrs:
            ip_prefix = cidr.split('/')
            subnets.append({
                'ip_prefix': ip_prefix[0],
                'ip_prefix_len': ip_prefix[1]
            })
        ns_fq_name = fab.fq_name + [ns_name]
        namespace = FabricNamespace(
            name=ns_name,
            fq_name=ns_fq_name,
            parent_type='fabric',
            fabric_namespace_type='IPV4-CIDR',
            fabric_namespace_value={
                'ipv4_cidr': {
                    'subnet': subnets
                },
            }
        )
        namespace.set_tag_list([{'to': ['label=fabric-management_ip']}])
        try:
            ns_uuid = self._api.fabric_namespace_create(namespace)
            namespace = self._api.fabric_namespace_read(id=ns_uuid)
        except RefsExistError:
            self._logger.warn(
                "Fabric namespace '%s' already exists", ns_name)
            namespace = self._api.fabric_namespace_read(fq_name=ns_fq_name)

        self._logger.debug(
            "Fabric namespace created:\n%s",
            pprint.pformat(self._api.obj_to_dict(namespace), indent=4))
        return namespace
    # end _add_mgmt_ip_namespace

    def add_asn_namespace(self, fab, asn):
        """add AS number as fabric namespace"""
        ns_name = "asn_%d" % asn
        self._logger.info(
            'Adding ASN namespace "%s" to fabric "%s" ...',
            ns_name, fab.name)

        ns_fq_name = fab.fq_name + [ns_name]
        namespace = FabricNamespace(
            name=ns_name,
            fq_name=ns_fq_name,
            parent_type='fabric',
            fabric_namespace_type='ASN',
            fabric_namespace_value={
                'asn': {
                    'asn': [asn]
                }
            }
        )
        namespace.set_tag_list([{'to': ['label=fabric-as_number']}])
        try:
            ns_uuid = self._api.fabric_namespace_create(namespace)
            namespace = self._api.fabric_namespace_read(id=ns_uuid)
        except RefsExistError:
            self._logger.warn(
                "Fabric namespace '%s' already exists", ns_name)
            namespace = self._api.fabric_namespace_read(fq_name=ns_fq_name)

        self._logger.debug(
            "Fabric namespace created:\n%s",
            pprint.pformat(self._api.obj_to_dict(namespace), indent=4))
        return namespace
    # end _add_asn_namespace

    def create_image(self, img_name, img_uri, img_version,
                                img_family, img_vendor):

        """create image"""
        img_fqname = None
        # device_fqname = None
        try:
            self._logger.info('Creating image: %s', img_name)
            img_fqname = ['default-global-system-config', img_name]
            image = DeviceImage(
                name=img_name,
                fq_name=img_fqname,
                parent_type='global-system-config',
                device_image_file_uri=img_uri,
                device_image_os_version=img_version,
                device_image_device_family=img_family,
                device_image_vendor_name=img_vendor
            )
            img_uuid = self._api.device_image_create(image)
            image = self._api.device_image_read(id=img_uuid)

        except RefsExistError:
            self._logger.warn("Image '%s' already exists", img_name)
            image = self._api.device_image_read(fq_name=img_fqname)

        self._logger.debug(
            "Image created:\n%s",
            pprint.pformat(self._api.obj_to_dict(image), indent=4))
        return image

    # end create_image_and_device

    def cleanup_fabric(self, fab_name):
        """delete fabric including all prouters in the fabric"""
        try:
            self._logger.info('Deleting fabric "%s" ...', fab_name)
            fab_fqname = ['default-global-system-config', fab_name]
            fab = self._api.fabric_read(fq_name=fab_fqname)

            # delete all namespaces in this fabric
            fab_namespaces = self._api.fabric_namespaces_list(
                parent_id=fab.uuid)
            for namespace in fab_namespaces.get('fabric-namespaces') or []:
                self._logger.debug(
                    "Delete namespace: %s", namespace.get('fq_name'))
                self._api.fabric_namespace_delete(namespace.get('fq_name'))

            # delete fabric
            self._logger.debug("Delete fabric: %s", fab_fqname)
            self._api.fabric_delete(fab_fqname)

            # delete all prouters in this fabric
            for prouter in fab.get_physical_router_back_refs() or []:
                self._delete_prouter(prouter.get('uuid'))

        except NoIdError:
            self._logger.warn('Fabric "%s" not found', fab_name)
    # end cleanup_fabric

    def cleanup_image(self, img_name,):
        # image cleanup
        self._logger.info("Clean up image and prouter from db")
        try:
            img_fqname = ['default-global-system-config', img_name]
            img = self._api.device_image_read(fq_name=img_fqname)
            self._logger.debug(
                "Delete Image: %s", img_fqname)
            self._api.device_image_delete(img_fqname)

        except NoIdError:
            self._logger.warn('Image "%s" not found', img_name)

    def _delete_prouter(self, uuid):
        prouter = self._api.physical_router_read(id=uuid)

        # delete all physical and logical interfaces
        ifds = self._api.physical_interfaces_list(parent_id=uuid)
        for ifd in ifds.get('physical-interfaces')  or []:
            # delete all child logical interfaces
            ifls = self._api.logical_interfaces_list(parent_id=ifd.get('uuid'))
            for ifl in ifls.get('logical-interfaces') or []:
                self._logger.debug(
                    "Delete logical interface: %s", ifl.get('fq_name'))
                self._api.logical_interface_delete(ifl.get('fq_name'))

            # delete the physical interface
            self._logger.debug(
                "Delete physical interface: %s", ifd.get('fq_name'))
            self._api.physical_interface_delete(ifd.get('fq_name'))

        # delete the prouter
        self._logger.debug(
            "Delete physical router: %s", prouter.get_fq_name())
        self._api.physical_router_delete(prouter.get_fq_name())

        # delete corresponding bgp routers
        for bgp_router_ref in prouter.get_bgp_router_refs() or []:
            self._logger.debug(
                "Delete bgp router: %s", bgp_router_ref.get('to'))
            self._api.bgp_router_delete(bgp_router_ref.get('to'))
    # end _delete_prouter

    @staticmethod
    def _get_job_status_query_payload(job_execution_id, status):
        return {
            'start_time': 'now-5m',
            'end_time': 'now',
            'select_fields': ['MessageTS', 'Messagetype'],
            'table': 'ObjectJobExecutionTable',
            'where': [
                [
                    {
                        'name': 'ObjectId',
                        'value': "%s:%s" % (job_execution_id, status),
                        'op': 1
                    }
                ]
            ]
        }
    # end _get_job_status_query_payload

    @staticmethod
    def _check_job_status(url, job_execution_id, job_status):
        payload = SanityBase._get_job_status_query_payload(job_execution_id,
                                                           job_status)
        r = requests.post(url, json=payload)
        if r.status_code == 200:
            response = r.json()
            if len(response['value']) > 0:
                assert response['value'][0]['Messagetype'] == 'JobLog'
                return True
        return False
    # end _post_for_json_response

    def _wait_for_job_to_finish(self, job_name, job_execution_id):
        completed = "SUCCESS"
        failed = "FAILURE"
        url = "http://%s:%d/analytics/query" %\
              (self._analytics['host'], self._analytics['port'])
        retry_count = 0
        while True:
            # check if job completed successfully
            if SanityBase._check_job_status(url, job_execution_id, completed):
                self._logger.debug("%s job '%s' finished", job_name,
                                   job_execution_id)
                break
            # check if job failed
            if SanityBase._check_job_status(url, job_execution_id, failed):
                self._logger.debug("%s job '%s' failed", job_name,
                                   job_execution_id)
                raise Exception("%s job '%s' failed" %
                                (job_name, job_execution_id))
            if retry_count > self._max_retries:
                raise Exception("Timed out waiting for '%s' job to complete" %
                                job_name)
            retry_count += 1
            time.sleep(self._timeout)
    # end _wait_for_job_to_finish

    def discover_fabric_device(self, fab):
        """Discover all devices specified by the fabric management namespaces
        """
        self._logger.info('Discover devices in fabric "%s" ...', fab.fq_name)
        job_execution_info = self._api.execute_job(
            job_template_fq_name=[
                'default-global-system-config', 'discover_device_template'],
            job_input={'fabric_uuid': fab.uuid}
        )

        job_execution_id = job_execution_info.get('job_execution_id')
        self._logger.debug(
            "Device discovery job started with execution id: %s",
            job_execution_id)
        self._wait_for_job_to_finish('Device discovery', job_execution_id)

        fab = self._api.fabric_read(fab.fq_name)
        discovered_prouter_refs = fab.get_physical_router_back_refs()
        self._logger.debug(
            "Disovered devices:\n%s",
            pprint.pformat(discovered_prouter_refs, indent=4))

        msg = "Discovered following devices in fabric '%s':" % fab.fq_name
        discovered_prouters = []
        for prouter_ref in discovered_prouter_refs:
            prouter = self._api.physical_router_read(prouter_ref.get('to'))
            discovered_prouters.append(prouter)
            msg += "\n - %s (%s)" % (
                prouter.name, prouter.physical_router_management_ip)

        self._logger.info(msg)
        return discovered_prouters
    # end discover_fabric_device

    def device_import(self, prouters):
        """import device inventories for the prouters specified in the
        argument"""
        self._logger.info("Import all discovered prouters in the fabric ...")
        job_execution_info = self._api.execute_job(
            job_template_fq_name=[
                'default-global-system-config', 'device_import_template'],
            job_input={},
            device_list=[prouter.uuid for prouter in prouters]
        )

        job_execution_id = job_execution_info.get('job_execution_id')
        self._logger.debug(
            "Device import job started with execution id: %s", job_execution_id)
        self._wait_for_job_to_finish('Device import', job_execution_id)

        for prouter in prouters:
            ifd_refs = self._api.physical_interfaces_list(
                parent_id=prouter.uuid)
            self._logger.info(
                "Imported %d physical interfaces to prouter: %s",
                len(ifd_refs.get('physical-interfaces')), prouter.name)
    # end device_import

    def underlay_config(self, prouters):
        """deploy underlay config to prouters in the fabric ..."""
        self._logger.info("Deploy underlay config to prouters in fabric ...")
        job_execution_info = self._api.execute_job(
            job_template_fq_name=[
                'default-global-system-config', 'generate_underlay_template'],
            job_input={
                'enable_lldp': 'true'
            },
            device_list=[prouter.uuid for prouter in prouters]
        )

        job_execution_id = job_execution_info.get('job_execution_id')
        self._logger.debug(
            "Device import job started with execution id: %s", job_execution_id)
        self._wait_for_job_to_finish('Underlay config', job_execution_id)
    # end underlay_config

    def image_upgrade(self, image, device):
        """upgrade the physical routers with specified images"""
        self._logger.info("Upgrade image on the physical router ...")
        job_execution_info = self._api.execute_job(
            job_template_fq_name=[
                'default-global-system-config', 'image_upgrade_template'],
            job_input={'image_uuid': image.uuid},
            device_list=[device.uuid]
        )
        job_execution_id = job_execution_info.get('job_execution_id')
        self._logger.info(
            "Image upgrade job started with execution id: %s", job_execution_id)
        self._wait_for_job_to_finish('Image upgrade', job_execution_id)

    # end image_upgrade

    def ztp(self, fabric_uuid):
        """run ztp for a fabric"""
        self._logger.info("Running ZTP for fabric...")
        job_execution_info = self._api.execute_job(
            job_template_fq_name=[
                'default-global-system-config', 'ztp_template'],
            job_input={'fabric_uuid': fabric_uuid, 'device_count': 1}
        )
        job_execution_id = job_execution_info.get('job_execution_id')
        self._logger.info(
            "ZTP job started with execution id: %s", job_execution_id)
        self._wait_for_job_to_finish('ZTP', job_execution_id)

    # end ztp

    def _exit_with_error(self, errmsg):
        self._logger.error(errmsg)
        sys.exit(1)
    # end _exit_with_error

# end SanityBase class
