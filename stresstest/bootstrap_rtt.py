from __future__ import print_function

from os import path
from random import randint
from socket import gethostbyname
import time

from twisted.internet import reactor

# Check if we are running from the root directory
# If not, modify our path so that we can import IPv8
try:
    import ipv8
    del ipv8
except ImportError:
    import sys
    sys.path.append(path.abspath(path.join(path.dirname(__file__), "..")))

from ipv8_service import _COMMUNITIES, IPv8
from ipv8.configuration import get_default_configuration
from ipv8.community import _DEFAULT_ADDRESSES, _DNS_ADDRESSES, Community
from ipv8.keyvault.crypto import ECCrypto
from ipv8.peer import Peer
from ipv8.requestcache import NumberCache, RequestCache


INSTANCES = []
CHECK_QUEUE = []
RESULTS = {}

CONST_REQUESTS = 10


class PingCache(NumberCache):

    def __init__(self, community, hostname, address, starttime):
        super(PingCache, self).__init__(community.request_cache, u"introping", community.global_time)
        self.hostname = hostname
        self.address = address
        self.starttime = starttime
        self.community = community

    @property
    def timeout_delay(self):
        return 5.0

    def on_timeout(self):
        self.community.finish_ping(self, False)


class MyCommunity(Community):
    master_peer = Peer(ECCrypto().generate_key(u"medium"))

    def __init__(self, *args, **kwargs):
        super(MyCommunity, self).__init__(*args, **kwargs)
        self.request_cache = RequestCache()

    def unload(self):
        self.request_cache.shutdown()
        super(MyCommunity, self).unload()

    def finish_ping(self, cache, include=True):
        global RESULTS
        print(cache.hostname, cache.address, time.time()-cache.starttime)
        if include:
            if (cache.hostname, cache.address) in RESULTS:
                RESULTS[(cache.hostname, cache.address)].append(time.time()-cache.starttime)
            else:
                RESULTS[(cache.hostname, cache.address)] = [time.time() - cache.starttime]

        self.next_ping()

    def next_ping(self):
        global CHECK_QUEUE
        if CHECK_QUEUE:
            hostname, address = CHECK_QUEUE.pop()
            packet = self.create_introduction_request(address)
            self.request_cache.add(PingCache(self, hostname, address, time.time()))
            self.endpoint.send(address, packet)
        else:
            reactor.callFromThread(reactor.stop)

    def introduction_response_callback(self, peer, dist, payload):
        if self.request_cache.has(u"introping", payload.identifier):
            cache = self.request_cache.pop(u"introping", payload.identifier)
            self.finish_ping(cache)

    def started(self):
        global CHECK_QUEUE

        dnsmap = {}
        for (address, port) in _DNS_ADDRESSES:
            try:
                ip = gethostbyname(address)
                dnsmap[(ip, port)] = address
            except:
                pass

        UNKNOWN_NAME = '*'

        for (ip, port) in _DEFAULT_ADDRESSES:
            hostname = dnsmap.get((ip, port), None)
            if not hostname:
                hostname = UNKNOWN_NAME
                UNKNOWN_NAME = UNKNOWN_NAME + '*'
            CHECK_QUEUE.append((hostname, (ip, port)))

        CHECK_QUEUE = CHECK_QUEUE * CONST_REQUESTS

        self.next_ping()


_COMMUNITIES['MyCommunity'] = MyCommunity

configuration = get_default_configuration()
configuration['keys'] = [{
    'alias': "my peer",
    'generation': u"medium",
    'file': u"ec1.pem"
}]
configuration['port'] = 12000 + randint(0, 10000)
configuration['overlays'] = [{
    'class': 'MyCommunity',
    'key': "my peer",
    'walkers': [],
    'initialize': {},
    'on_start': [('started', )]
}]
INSTANCES.append(IPv8(configuration))

reactor.run()

with open('summary.txt', 'w') as f:
    f.write('HOST_NAME ADDRESS REQUESTS RESPONSES')
    for key in RESULTS:
        hostname, address = key
        f.write('\n%s %s:%d %d %d' % (hostname, address[0], address[1], CONST_REQUESTS, len(RESULTS[key])))

with open('walk_rtts.txt', 'w') as f:
    f.write('HOST_NAME ADDRESS RTT')
    for key in RESULTS:
        hostname, address = key
        for rtt in RESULTS[key]:
            f.write('\n%s %s:%d %f' % (hostname, address[0], address[1], rtt))
