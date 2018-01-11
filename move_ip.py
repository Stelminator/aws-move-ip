import sys
import time

import boto3
from ec2_metadata import ec2_metadata


if __name__ == '__main__':
    if len(sys.argv[1:]) != 3:
        raise Exception('wrong number of arguments (!=3)')
    region = ec2_metadata.region
    instance_id = ec2_metadata.instance_id

    access_key_id = sys.argv[1]
    access_key_secret = sys.argv[2]
    public_ip = sys.argv[3]

    client = boto3.client('ec2',
                          region_name=region,
                          aws_access_key_id=access_key_id,
                          aws_secret_access_key=access_key_secret,
                          )

    current_addresses = client.describe_addresses(Filters=[
        {
            'Name': 'instance-id',
            'Values': [instance_id],
        }
    ])['Addresses']

    if current_addresses and current_addresses[0]['PublicIp'] == public_ip:
        print("already have that address")
        sys.exit(0)
    elif current_addresses:
        raise Exception('instance already has different EIP')

    is_vpc_instance = bool(client.describe_instances(Filters=[
        {
            'Name': 'instance-id',
            'Values': [instance_id],
        }
    ]).get('Reservations')[0].get('Instances')[0].get('VpcId'))

    address = client.describe_addresses(PublicIps=[public_ip])['Addresses'][0]

    is_vpc_address = address.get('Domain') == 'vpc'

    if is_vpc_instance != is_vpc_address:
        if is_vpc_address:
            desired = 'standard'
            # if not already associated, great
            if 'AssociationId' in address:
                print("disassociating", address['AssociationId'])
                client.disassociate_address(
                    AssociationId=address['AssociationId'],
                )
            print("restoring", public_ip, "to classic")
            response = client.restore_address_to_classic(
                PublicIp=public_ip
            )
        else:
            desired = 'vpc'
            # not really a way to check, this call should work anyway
            print("disassociating", public_ip)
            client.disassociate_address(
                PublicIp=public_ip
            )
            print("moving", public_ip, "to vpc")
            response = client.move_address_to_vpc(
                PublicIp=public_ip
            )

        for x in range(5):
            print("checking on address migration", x)
            address = client.describe_addresses(
                PublicIps=[public_ip])['Addresses'][0]
            if address['PublicIp'] != public_ip:
                raise AssertionError("failed to find address '%s', got '%s' instead." % (
                    public_ip, address['PublicIp']))
            if address.get('Domain') == desired:
                is_vpc_address = address.get('Domain') == 'vpc'
                break
            time.sleep(6)
        else:
            print("timed out moving address '%s' to: '%s' Domain" % (public_ip, desired))
            sys.exit(1)

    if is_vpc_instance:
        print("associating", address['AllocationId'], "to", instance_id)
        client.associate_address(
            AllocationId=address['AllocationId'],
            InstanceId=instance_id,
            AllowReassociation=True,
        )
    else:
        print("associating", public_ip, "to", instance_id)
        client.associate_address(
            InstanceId=instance_id,
            PublicIp=public_ip,
        )
    print("Completed")
