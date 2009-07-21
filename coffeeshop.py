# coffeeshop
# A lightweight REST-orientated pubsub mechanism
# (c) 2009 DJ Adams
# See https://github.com/qmacro/coffeeshop/

import os
import re
import cgi
import logging
import wsgiref.handlers
import datetime

from models import Channel, Subscriber, Message, Delivery
from bucket import agoify

from google.appengine.ext.webapp import template
from google.appengine.ext import webapp
from google.appengine.ext import db
from google.appengine.api.labs import taskqueue

VERSION = "0.01"

#     ***************
class MainPageHandler(webapp.RequestHandler):
#     ***************
  def get(self):
    template_values = {
      'version': VERSION,
      'server_software': os.environ.get("SERVER_SOFTWARE", "unknown"),
    }
    path = os.path.join(os.path.dirname(__file__), 'index.html')
    self.response.out.write(template.render(path, template_values))

#     ***********************
class ChannelContainerHandler(webapp.RequestHandler):
#     ***********************
  """Handler for main /channel/ resource
  """
  def get(self):
    """Show list of channels
    """
#   TODO: paging
    channels = []
    for channel in db.GqlQuery("SELECT * FROM Channel ORDER BY created DESC"):
      channels.append({
        'channelid': channel.key().id(),
        'name': channel.name,
        'created': channel.created,
        'created_ago': agoify(channel.created),
      })
    template_values = {
      'channels': channels,
    }
    path = os.path.join(os.path.dirname(__file__), 'channel_list.html')
    self.response.out.write(template.render(path, template_values))

  def post(self):
    """Handles a POST to the /channel/ resource
    Creates a new channel resource (/channel/{id}) and returns
    its Location with a 201
    """
    channel = Channel()
    name = self.request.get('name').rstrip('\n')
    channel.name = name
    channel.put()
#   Not sure I like this ... re-put()ing
    if len(channel.name) == 0:
      channel.name = 'channel-' + str(channel.key().id())
      channel.put()

    # If we've got here from a web form, redirect the user to the 
    # channel list, otherwise return the 201
    if self.request.get('channelsubmissionform'):
      self.redirect('/channel/')
    else:
      self.response.headers['Location'] = '/channel/' + str(channel.key().id()) + '/'
      self.response.set_status(201)


#     ****************************
class ChannelSubmissionformHandler(webapp.RequestHandler):
#     ****************************
  """Handles the channel submission form resource
  /channel/submissionform/
  """
  def get(self):
    """Renders channel submission form, that has a POST action to
    the /channel/ resource
    """
    path = os.path.join(os.path.dirname(__file__), 'channelsubmissionform.html')
    self.response.out.write(template.render(path, {}))


#     **************
class ChannelHandler(webapp.RequestHandler):
#     **************
  """Handles an individual channel resource
  e.g. /channel/123/
  Shows when it was created, and a link to subscribers (if there are any)
  """
  def _getchannel(self, channelid):
    # TODO refactor this into a base class
    channel = Channel.get_by_id(int(channelid))
    if channel is None:
      self.response.out.write("Channel %s not found" % (channelid, ))
      self.response.set_status(404)
    return channel
    
  def get(self, channelid):
    channel = self._getchannel(channelid)
    if channel is None: return

    anysubscribers = Subscriber.all().filter('channel =', channel).fetch(1)
    
    template_values = {
      'channel': channel,
      'anysubscribers': anysubscribers,
    }
    path = os.path.join(os.path.dirname(__file__), 'channel_detail.html')
    self.response.out.write(template.render(path, template_values))


  def post(self, channelid):
    channel = self._getchannel(channelid)
    if channel is None: return

    # Save message
    message = Message(
      contenttype = self.request.headers['Content-Type'],
      body = self.request.body,
      channel = channel,
    )
    message.put()

    for subscriber in Subscriber.all().filter('channel =', channel):
      logging.info(subscriber.name)

      # Set up delivery of message to subscriber
      delivery = Delivery(
        message = message,
        recipient = subscriber,
      )
      delivery.put()

    # TODO should we return a 202 instead of a 302?
    self.redirect(self.request.url + 'message/' + str(message.key()))


#     **************************************
class ChannelSubscriberSubmissionformHandler(webapp.RequestHandler):
#     **************************************
  """Handles the subscriber submission form for a given channel,
  i.e. resource /channel/{id}/subscriber/submissionform
  """
  def get(self, channelid):
    """Handles a GET to the /channel/{id}/subscriber/submissionform resource
    """
    channel = Channel.get_by_id(int(channelid))
    if channel is None:
      self.response.out.write("Channel %s not found" % (channelid, ))
      self.response.set_status(404)
      return

    template_values = {
      'channel': channel,
      'channelsubscriberresource': '/channel/' + channelid + '/subscriber/',
    }
    path = os.path.join(os.path.dirname(__file__), 'subscribersubmissionform.html')
    self.response.out.write(template.render(path, template_values))


#     *********************************
class ChannelSubscriberContainerHandler(webapp.RequestHandler):
#     *********************************
  """Handles the subscribers for a given channel, i.e. resource
  /channel/{id}/subscriber/
  """
  def get(self, channelid):
    """Handles a GET to the /channel/{id}/subscriber/ resource
    """
    channel = Channel.get_by_id(int(channelid))
    if channel is None:
      self.response.out.write("Channel %s not found" % (channelid, ))
      self.response.set_status(404)
      return

    subscribers = []
    for subscriber in Subscriber.all().filter('channel =', channel):
      subscribers.append({
        'subscriberid': subscriber.key().id(),
        'name': subscriber.name,
        'resource': subscriber.resource,
        'created': subscriber.created,
      })

    template_values = {
      'channel': channel,
      'subscribers': subscribers,
    }
    path = os.path.join(os.path.dirname(__file__), 'channelsubscriber.html')
    self.response.out.write(template.render(path, template_values))

  def post(self, channelid):
    """Handles a POST to the /channel/{id}/subscriber/ resource
    which is to add a subscriber to the channel
    """
#   Get channel first
    channel = Channel.get_by_id(int(channelid))
    if channel is None:
      self.response.out.write("Channel %s not found" % (channelid, ))
      self.response.set_status(404)
      return

#   Add subscriber
    name = self.request.get('name').rstrip('\n')
    resource = self.request.get('resource').rstrip('\n')
    subscriber = Subscriber()
    subscriber.channel = channel
    subscriber.name = name
    subscriber.resource = resource
    subscriber.put()
#   Not sure I like this ... re-put()ing
    if len(subscriber.name) == 0:
      subscriber.name = 'subscriber-' + str(subscriber.key().id())
      subscriber.put()

#   If we've got here from a web form, redirect the user to the 
#   channel subscriber resource, otherwise return the 201
    if self.request.get('subscribersubmissionform'):
      self.redirect(self.request.path_info)
    else:
      self.response.headers['Location'] = '/channel/' + channelid + '/subscriber/' + str(subscriber.key().id()) + '/'
      self.response.set_status(201)


#     ************************
class ChannelSubscriberHandler(webapp.RequestHandler):
#     ************************
  """Handles a given channel subscriber, i.e. resource
  /channel/{id}/subscriber/{id}/
  """
  def get(self, channelid, subscriberid):
    channel = Channel.get_by_id(int(channelid))
    if channel is None:
      self.response.out.write("Channel %s not found" % (channelid, ))
      self.response.set_status(404)
      return

    subscriber = Subscriber.get_by_id(int(subscriberid))
    if subscriber is None:
      self.response.out.write("Subscriber %s for channel %s not found" % (subscriberid, channelid))
      self.response.set_status(404)
      return

    template_values = {
      'channel': channel,
      'subscriber': subscriber,
    }
    path = os.path.join(os.path.dirname(__file__), 'subscriber_detail.html')
    self.response.out.write(template.render(path, template_values))


#     **************************
class SubscriberContainerHandler(webapp.RequestHandler):
#     **************************
  """Handles the subscriber container resource, i.e.
  /subscriber/
  GET will just return a list of subscribers, by channel
  """
  def get(self):
    subscribers = db.GqlQuery("SELECT * FROM Subscriber "
                                  "ORDER BY channel ASC, created DESC")
    template_values = {
      'subscribers': subscribers,
    }
    path = os.path.join(os.path.dirname(__file__), 'subscriber.html')
    self.response.out.write(template.render(path, template_values))
    

class ChannelMessageHandler(webapp.RequestHandler):
  """Handles message delivery status resources in the form of
  /channel/{cid}/message/{mid}
  """
  def get(self, channelid, messageid):
    message = Message.get(messageid)
    if message is None:
      self.response.out.write("Message %s not found" % (messageid, ))
      self.response.set_status(404)
      return

    template_values = {
      'message': message,
      'deliveries': Delivery.all().filter('message =', message),
    }
    path = os.path.join(os.path.dirname(__file__), 'messagedetail.html')
    self.response.out.write(template.render(path, template_values))
    self.response.set_status(200)


class ChannelMessageContainerHandler(webapp.RequestHandler):
  """Handles the message container resource for a channel, in the form of
  /channel/{cid}/message/
  """
  def _getchannel(self, channelid):
    # TODO refactor this into a base class
    channel = Channel.get_by_id(int(channelid))
    if channel is None:
      self.response.out.write("Channel %s not found" % (channelid, ))
      self.response.set_status(404)
    return channel
    
  def get(self, channelid):
    channel = self._getchannel(channelid)
    if channel is None: return

    template_values = {
      'channel': channel,
      'messages': Message.all().filter('channel =', channel),
    }
    path = os.path.join(os.path.dirname(__file__), 'messagelist.html')
    self.response.out.write(template.render(path, template_values))
    self.response.set_status(200)


class ChannelMessageSubmissionformHandler(webapp.RequestHandler):
  """Handles the channel message submission form for a given channel,
  i.e. resource /channel/{id}/message/submissionform
  """
  def _getchannel(self, channelid):
    # TODO refactor this into a base class
    channel = Channel.get_by_id(int(channelid))
    if channel is None:
      self.response.out.write("Channel %s not found" % (channelid, ))
      self.response.set_status(404)
    return channel
    
  def get(self, channelid):
    channel = self._getchannel(channelid)
    if channel is None: return

    template_values = {
      'channel': channel,
    }
    path = os.path.join(os.path.dirname(__file__), 'messagesubmissionform.html')
    self.response.out.write(template.render(path, template_values))



#class ReflectHandler(webapp.RequestHandler):
#  """Task Queue handler - accepts a URL and a payload entity and
#  makes a POST request
#  """
#  def post(self,

def main():
  application = webapp.WSGIApplication([
    (r'/', MainPageHandler),
    (r'/channel/submissionform/?', ChannelSubmissionformHandler),
    (r'/channel/(.+?)/subscriber/submissionform', ChannelSubscriberSubmissionformHandler),
    (r'/channel/(.+?)/subscriber/', ChannelSubscriberContainerHandler),
    (r'/channel/(.+?)/subscriber/(.+?)/', ChannelSubscriberHandler),
    (r'/channel/(.+?)/message/submissionform/?', ChannelMessageSubmissionformHandler),
    (r'/channel/(.+?)/message/(.+)', ChannelMessageHandler),
    (r'/channel/(.+?)/message/', ChannelMessageContainerHandler),
    (r'/channel/(.+?)/', ChannelHandler),
    (r'/channel/?', ChannelContainerHandler),
    (r'/subscriber/', SubscriberContainerHandler),
#   (r'/reflect/', ReflectHandler),
  ], debug=True)
  wsgiref.handlers.CGIHandler().run(application)


if __name__ == "__main__":
  main()




