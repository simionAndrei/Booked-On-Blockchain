import glob
import hashlib
import json
import os
from collections import defaultdict

from twisted.internet import reactor

from pyipv8 import NewCommunityCreatedEvent, NewCommunityRegisteredEvent
from pyipv8.ipv8.attestation.bobchain.community import BOBChainCommunity
from pyipv8.ipv8.keyvault.crypto import ECCrypto
from pyipv8.ipv8.peer import Peer
from pyipv8.ipv8.peerdiscovery.discovery import EdgeWalk, RandomWalk


def construct_communities():
    return defaultdict(construct_communities)


communities = construct_communities()

_WALKERS = {
    'EdgeWalk': EdgeWalk,
    'RandomWalk': RandomWalk
}


class Controller:
    controller = None

    def __init__(self, ipv8):
        self.ipv8 = ipv8
        Controller.controller = self
        NewCommunityCreatedEvent.event.append(self.register_existing_community)

    def get_communities(self):
        return communities

    def get_bookings(self, property_details):
        country = property_details["country"]
        state = property_details["state"]
        city = property_details["city"]
        street = property_details["street"]
        number = property_details["number"]
        return communities[country][state][city][street][number].get_bookings()

    def register_existing_community(self, community):
        print "Register exiting community %s with peer %s...." %  (community, community.my_peer)
        communities[community.country][community.state][community.city][community.street][community.number] = community
        NewCommunityRegisteredEvent.event()

    def create_community(self, country, state, city, street, number):
        property_details = {"country": country,
                            "state": state,
                            "city": city,
                            "street": street,
                            "number": number}
        community_key = ECCrypto().generate_key(u"medium")
        community_peer = Peer(community_key)
        print "Community peer %s ...." % community_peer
        community = BOBChainCommunity(community_peer, self.ipv8.endpoint, self.ipv8.network, **property_details)
        self.ipv8.overlays.append(community)
        for walker in [{
            'strategy': "EdgeWalk",
            'peers': 20,
            'init': {
                'edge_length': 4,
                'neighborhood_size': 6,
                'edge_timeout': 3.0
            }
        }]:
            strategy_class = _WALKERS.get(walker['strategy'],
                                          community.get_available_strategies().get(walker['strategy']))
            args = walker['init']
            target_peers = walker['peers']
            self.ipv8.strategies.append((strategy_class(community, **args), target_peers))
        for config in [('started',)]:
            reactor.callWhenRunning(getattr(community, config[0]), *config[1:])
        communities[country][state][city][street][number] = community

        community_key_hash = hashlib.sha224(json.dumps(property_details)).hexdigest()
        with open("keys\\" + str(community_key_hash) + ".pem", 'w') as f:
            f.write(community_key.key_to_bin())

        with open('property_to_key_mappings.json', 'w') as file:
            l = []
            for country, states in communities.items():
                for state, cities in states.items():
                    for city, streets in cities.items():
                        for street, numbers in streets.items():
                            for number in numbers:
                                l.append([{
                                    "country": country,
                                    "state": state,
                                    "city": city,
                                    "street": street,
                                    "number": number,
                                }, community_key_hash])
            json.dump(l, file)

    def book_apartment(self, property_details, start_day, end_day):
        country = property_details["country"]
        state = property_details["state"]
        city = property_details["city"]
        street = property_details["street"]
        number = property_details["number"]
        return communities[country][state][city][street][number].book_apartment(start_day, end_day)

    def remove_all_created_blocks(self):
        for country, states in communities.items():
            for state, cities in states.items():
                for city, streets in cities.items():
                    for street, numbers in streets.items():
                        for number in numbers:
                            communities[country][state][city][street][number].remove_all_created_blocks()

        for f in glob.glob("keys\\*"):
            os.remove(f)

        with open('property_to_key_mappings.json', 'w') as file:
            json.dump([], file)
