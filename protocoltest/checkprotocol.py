#!/usr/bin/python2.5

import unittest
import httplib, urllib, re
import logging, sys

HUBROOT = 'giant:8888'
SUBROOT = 'giant:8889'
LOGFILE = 'unittest.log'
SUBSCRIBER_CONTAINER = 'subscriber/'
MESSAGE_CONTAINER = 'message/'

logger = None

# Relative resource patterns
CHANNEL = r'^\/channel\/(\d+)\/$'
SUBSCRIBER = r'^\/channel\/\d+\/subscriber\/(\d+)\/$'
MESSAGE = r'^\/channel\/\d+\/message\/(\w+)$'

# Helper functions
def myfuncname():
  """Returns name of caller function"""
  return sys._getframe(1).f_code.co_name

def log(message, callhier=1):
  """Logs at debug level a given message. By default will
  log the name of the caller, but this can be overridden
  by use of the callhier parameter"""
  # callhier=1 : gets the name of this function's caller

  # Only log if we're called directly (so we can use
  # this in immediate mode too)
  if __name__ == "__main__":
    caller = sys._getframe(callhier).f_code.co_name
    logger.debug("%s: %s" % (caller, message))


def newChannel(conn, name="Channel A"):
  """Creates new channel via POST to the /channel/ resource"""
  data = urllib.urlencode({ 'name': name })
  conn.request("POST", "/channel/", data)
  res = conn.getresponse()
  location = res.getheader('Location')
  idsearch = re.search(CHANNEL, location)
  log("created channel %s (%s)" % (location, name), 2)
  return (res.status, location, idsearch.group(1))

def newSubscriber(conn, cid, name="Subscriber A", resource="http://localhost"):
  """Creates new subscriber via POST to the given channel's resource"""
  data = urllib.urlencode({ 'name': name, 'resource': resource })
  conn.request("POST", "/channel/%s/subscriber/" % cid, data)
  res = conn.getresponse()
  location = res.getheader('Location')
  idsearch = re.search(SUBSCRIBER, location)
  log("created subscriber %s" % location, 2)
  return (res.status, location, idsearch.group(1))

def newMessage(conn, cid, message="the message"):
  """Publishes a new message to the given channel"""
  data = message
  conn.request("POST", "/channel/%s/" % cid, data)
  res = conn.getresponse()
  if res.status == 201:
    location = res.getheader('Location')
    idsearch = re.search(MESSAGE, location)
    return (res.status, location, idsearch.group(1))
  else:
    return (res.status, None, None)



class BasicTests(unittest.TestCase):

  def setUp(self):
    self.conn = httplib.HTTPConnection(HUBROOT)

  def tearDown(self):
    self.conn = None

  def testStartPageExists(self):
    """Check the start page exists"""
    self.conn.request("GET", "/")
    res = self.conn.getresponse()
    self.assertEqual(res.status, 200)


class ChannelTests(unittest.TestCase):
  
  def setUp(self):
    self.conn = httplib.HTTPConnection(HUBROOT)

  def tearDown(self):
    self.conn = None

  def testChannelContainerExists(self):
    """The channel container page exists"""
    self.conn.request("GET", "/channel/")
    res = self.conn.getresponse()
    self.assertEqual(res.status, 200)

  def testChannelCreationStatus(self):
    """A channel can be created"""
    status, location, cid = newChannel(self.conn, myfuncname())
    self.assertEqual(status, 201)
    
  def testDuplicateChannelName(self):
    """A name can be used for more than one channel"""
    status, location, cid = newChannel(self.conn, myfuncname())
    self.assertEqual(status, 201)
    status, location, cid = newChannel(self.conn, myfuncname())
    self.assertEqual(status, 201)
    
  def testChannelCreationLocation(self):
    """A valid Location is returned for a created channel"""
    status, location, cid = newChannel(self.conn, myfuncname())
    self.assertTrue(re.search(CHANNEL, location))

  def testChannelInfo(self):
    """There is channel info available"""
    # Create the channel first
    status, location, cid = newChannel(self.conn, myfuncname())

    # Check we have channel info - 
    # We're looking for a 200, and "No subscribers"
    self.conn.request("GET", location)
    res = self.conn.getresponse()

    self.assertEqual(res.status, 200)
    self.assertTrue(re.search('No subscribers', res.read()))

  def testInvalidChannelId(self):
    """Get 404 when the channel id is non-numeric"""
    self.conn.request("GET", "/channel/nonnumeric/")
    res = self.conn.getresponse()
    self.assertEqual(res.status, 404)

  def testChannelNotFound(self):
    """404 is returned for non-existent channel"""
    self.conn.request("GET", "/channel/9999999/")
    res = self.conn.getresponse()
    self.assertEqual(res.status, 404)

  def testZeroChannelNotFound(self):
    """404 is returned for channel zero"""
    self.conn.request("GET", "/channel/0/")
    res = self.conn.getresponse()
    self.assertEqual(res.status, 404)

  def testChannelNoSubsDelete(self):
    """A channel without subscribers can be deleted"""

    # Create a channel
    status, location, cid = newChannel(self.conn, myfuncname())
    self.assertTrue(re.search(CHANNEL, location))

    # A new channel won't have subscribers, but check
    self.conn.request("GET", location)
    getres = self.conn.getresponse()
    self.assertTrue(re.search('No subscribers', getres.read()))

    # Delete the channel, expect 204
    self.conn.request("DELETE", location)
    deleteres = self.conn.getresponse()
    self.assertEquals(deleteres.status, 204)


  def testChannelWithSubsNoDelete(self):
    """A channel with subscribers cannot be deleted"""

    # Create a channel
    status, location, cid = newChannel(self.conn, myfuncname())
    self.assertTrue(re.search(CHANNEL, location))

    # Add a subscriber
    sstatus, slocation, sid = newSubscriber(self.conn, cid, myfuncname(), 
      "http://%s/subscriber/%s" % (SUBROOT, myfuncname()))
    self.assertEqual(sstatus, 201)

    # Try to delete the channel, expect 405 + Allow header
    self.conn.request("DELETE", location)
    deleteres = self.conn.getresponse()
    self.assertEquals(deleteres.status, 405)
    self.failIf(deleteres.getheader('Allow') is None)

    
class SubscriberTests(unittest.TestCase):
  
  def setUp(self):
    self.conn = httplib.HTTPConnection(HUBROOT)

  def tearDown(self):
    self.conn = None

  def testSubscriberContainerResourceExists(self):
    """A subscriber container resource exists for a channel"""
    # Create the channel first
    status, location, cid = newChannel(self.conn, myfuncname())

    # GET the subscriber container
    self.conn.request("GET", location + SUBSCRIBER_CONTAINER)
    res = self.conn.getresponse()
    log("retrieve %s%s : %s" % (location, SUBSCRIBER_CONTAINER, res.status))
    self.assertEqual(res.status, 200)

  def testSubscriberCreationStatus(self):
    """A subscriber can be created and returns status 201"""

    # Create the channel first
    cstatus, clocation, cid = newChannel(self.conn, myfuncname())

    # Create the subscriber
    sstatus, slocation, sid = newSubscriber(self.conn, cid, myfuncname(), 
      "http://%s/subscriber/%s" % (SUBROOT, myfuncname()))

    self.assertEqual(sstatus, 201)

  def testSubscriberCreationLocation(self):
    """A subscriber can be created and a valid Location is returned"""

    # Create the channel first
    cstatus, clocation, cid = newChannel(self.conn, myfuncname())

    # Create the subscriber
    sstatus, slocation, sid = newSubscriber(self.conn, cid, myfuncname(), 
      "http://%s/subscriber/%s" % (SUBROOT, myfuncname()))

    self.assertTrue(re.search(SUBSCRIBER, slocation))

  def testDuplicateSubscriberName(self):
    """A channel can have multiple subscribers with the same name"""

    # Create the channel first
    cstatus, clocation, cid = newChannel(self.conn, myfuncname())

    # Create the first subscriber
    s1status, s1location, s1id = newSubscriber(self.conn, cid, myfuncname(), 
      "http://%s/subscriber/%s/1" % (SUBROOT, myfuncname()))
    self.assertEqual(s1status, 201)

    # Create the second subscriber, same name, different resource
    s2status, s2location, s2id = newSubscriber(self.conn, cid, myfuncname(), 
      "http://%s/subscriber/%s/2" % (SUBROOT, myfuncname()))
    self.assertEqual(s2status, 201)

  def testDuplicateSubscriberResource(self):
    """A channel can have multiple subscribers with the same resource"""

    # Create the channel first
    cstatus, clocation, cid = newChannel(self.conn, myfuncname())

    # Create the first subscriber
    s1status, s1location, s1id = newSubscriber(self.conn, cid, "%s 1" % myfuncname(), 
      "http://%s/subscriber/%s" % (SUBROOT, myfuncname()))
    self.assertEqual(s1status, 201)

    # Create the second subscriber, different name, same resource
    s2status, s2location, s2id = newSubscriber(self.conn, cid, "%s 2" % myfuncname(), 
      "http://%s/subscriber/%s" % (SUBROOT, myfuncname()))
    self.assertEqual(s2status, 201)

  def testSubscriberNoDeliveriesDelete(self):
    """A subscriber with no deliveries outstanding may be deleted"""

    # Create the channel first
    cstatus, clocation, cid = newChannel(self.conn, myfuncname())

    # Create the subscriber
    sstatus, slocation, sid = newSubscriber(self.conn, cid, myfuncname(), 
      "http://%s/subscriber/%s" % (SUBROOT, myfuncname()))

    # Try to delete the subscriber, expect 204
    self.conn.request("DELETE", slocation)
    deleteres = self.conn.getresponse()
    self.assertEquals(deleteres.status, 204)


  def testSubscriberWithDeliveriesNoDelete(self):
    """A subscriber with deliveries outstanding may not be deleted"""

    # Create the channel first
    cstatus, clocation, cid = newChannel(self.conn, myfuncname())

    # Create the subscriber with an undeliverable resource
    # (If we're running these tests on the SDK development server,
    # the deliveries won't be started automatically anyway, so will
    # remain outstanding)
    sstatus, slocation, sid = newSubscriber(self.conn, cid, myfuncname(), 
      "http://bad.coffeeshop.subscriber")
    self.assertEqual(sstatus, 201)

    # Publish a message
    mstatus, mlocation, mid = newMessage(self.conn, cid, myfuncname())

    # Try to delete the subscriber, expect 405 + Allow header
    self.conn.request("DELETE", slocation)
    deleteres = self.conn.getresponse()
    self.assertEquals(deleteres.status, 405)
    self.failIf(deleteres.getheader('Allow') is None)


class MessageTests(unittest.TestCase):
  
  def setUp(self):
    self.conn = httplib.HTTPConnection(HUBROOT)

  def tearDown(self):
    self.conn = None

  def testMessageContainerExists(self):
    """The message container for a channel exists"""
    # Create the channel first
    status, location, cid = newChannel(self.conn, myfuncname())
    self.assertTrue(re.search(CHANNEL, location))

    # GET the message container
    self.conn.request("GET", location + MESSAGE_CONTAINER)
    res = self.conn.getresponse()
    log("retrieve %s%s : %s" % (location, MESSAGE_CONTAINER, res.status))
    self.assertEqual(res.status, 200)

  def testMessageToNonExistentChannel(self):
    """A message cannot be published to a nonexistent channel"""
    status, location, mid = newMessage(self.conn, 99999, myfuncname())
    self.assertEqual(status, 404)






if __name__ == '__main__':
  logger = logging.getLogger("unitlogger")
  logger.setLevel(logging.DEBUG)
  loghandler = logging.FileHandler(LOGFILE, "w")
  loghandler.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
  loghandler.setLevel(logging.DEBUG)
  logger.addHandler(loghandler)

  unittest.main()
  
