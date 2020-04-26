import appdaemon.plugins.hass.hassapi as hass
import pprint
import six

ALARM_STATES = ['disarmed', 'armed_night', 'armed_away', 'armed_home']
ALARM_SERVICES = ['alarm_disarm', 'alarm_arm_night', 'alarm_arm_away', 'alarm_arm_home']



class TelegramBotEventListener(hass.Hass):
    """Event listener for Telegram bot events."""

    def initialize(self):
        #config validation
        self.aircon_configured = False
        self.alarm_configured = False
        self.temperature_configured = False
        if "aircon" in self.args.keys():
            if self.entity_exists(self.args['aircon']):
                self.aircon_configured = True
        if "alarm" in self.args.keys():
            if "control" in self.args['alarm'].keys():
                if self.entity_exists(self.args['alarm']['control']):
                    self.alarm_configured = True
        if "temp_group" in self.args.keys():
            self.temperature_configured = True
            
        #initial states
        self.receiving_alarm_pin = False
        
        #logging
        self.logger = self.get_user_log("test_log")
    
        """Listen to Telegram Bot events of interest."""
        self.listen_event(self.receive_telegram_command, 'telegram_command')
        self.listen_event(self.receive_telegram_callback, 'telegram_callback')
        self.listen_event(self.receive_telegram_text, "telegram_text")
        
    def process_commands(self, command, user_id, user_name, args):
        ret = True
        msg = None
        keyboard = None
        
        if command == "/hello" or command == "/help":
            msg, keyboard = self.hello_command(user_id, user_name, args)
        elif command == "/aircon" and self.aircon_configured:
            msg, keyboard = self.aircon_command(user_id, user_name, args)
        elif command == "/aircon_set" and self.aircon_configured: 
            msg, keyboard = self.aircon_set_command(user_id, user_name, args)
        elif command == "/alarm" and self.alarm_configured:
            msg, keyboard = self.alarm_command(user_id, user_name, args)
        elif command == "/alarm_set" and self.alarm_configured:
            msg, keyboard = self.alarm_set_command(user_id, user_name, args)    
        elif command == "/temps" and self.temperature_configured:
            msg, keyboard = self.temps_command(user_id, user_name, args)
        elif command == "/do_nothing":
            msg = "Goodbye"
        else:
            ret = False
            
        return ret, msg, keyboard 
            
    def process_callback_only_commands(self, command, user_id, user_name):
        ret = True
        msg = None
        keyboard = None
        
        if command == "/do_nothing":
            msg = "Goodbye"
        else:
            ret = False
        
        return ret, msg, keyboard 

    def hello_command(self, user_id, user_name, args):
        msg = "Hello {}. What would you like to know?:".format(user_name)
        
        #decide what buttons to display
        buttons = []
        if self.aircon_configured:
            buttons.append(("Aircon", "/aircon"))
        if self.alarm_configured:
            buttons.append(("Alarm", "/alarm"))
        if self.temperature_configured:
            buttons.append(("Temperatures", "/temps"))
        buttons.append(("Goodbye", "/do_nothing"))
        
        #put into rows of 2
        row = []
        keyboard = []
        for b in buttons:
            row.append(b)
            if len(row) >= 2:
                keyboard.append(row)
                row = []
        #last row
        if len(row) > 0:
            keyboard.append(row)
                                                    
        return msg, keyboard
    
    #Info about aircon and keyboard for aircon actions
    def aircon_command(self, user_id, user_name, args):
        aircon_state = self.get_state(self.args["aircon"])
        aircon_current_temp = self.get_state(self.args["aircon"], 'current_temperature')
        aircon_setpoint_temp = self.get_state(self.args["aircon"], 'temperature')
        
        msg = "Airconditioner is currently set to {}. Current temperature is {} degrees.".format(aircon_state, aircon_current_temp)
        if aircon_state in ["cool", "heat", "heat_cool"]:
            msg += "Setpoint is {} degrees".format(aircon_setpoint_temp)
              
        keyboard = [[("Off", "/aircon_set off"), ("Fan", "/aircon_set fan_only"), ("Cool", "/aircon_set cool")],
                    [("Heat", "/aircon_set heat"), ("Goodbye", "/do_nothing")]]
            
        return msg, keyboard
    
    #Changing aircon state
    def aircon_set_command(self, user_id, user_name, args):
        msg = "Unknown aircon mode"
        aircon_supported_modes = self.get_state(self.args["aircon"], 'hvac_modes')
        if len(args) == 1:
            if args[0] in aircon_supported_modes:
                self.call_service('climate/set_hvac_mode', entity_id = self.args["aircon"], hvac_mode=args[0])
                msg= 'Aircon changed to {}'.format(args[0])
        return msg, None
        
    #Info about alarm and keyboard for alarm actions        
    def alarm_command(self, user_id, user_name, args):
        alarm_state = self.get_state(self.args["alarm"]["control"])
        
        msg = "Alarm is currently {}\n".format(str(alarm_state).replace("_", " "))

        msg += self.alarm_sensor_states()
        
        keyboard = [[("Disarm", "/alarm_set disarm"), ("Arm Night", "/alarm_set arm_night")],
                    [("Arm Away", "/alarm_set arm_away"), ("Goodbye", "/do_nothing")]]
                    
        return msg, keyboard
    
    #print alarm sensor states
    def alarm_sensor_states(self):
        msg = ""

        if self.entity_exists(self.args["alarm"]["sensor_group"]):
            sensor_group = self.get_state(self.args["alarm"]["sensor_group"], "entity_id")
            
            #iterate entity group
            for s in sensor_group:
                this_sensor_name = self.get_state(s, "friendly_name")
                this_sensor_state = self.get_state(s)
                this_sensor_device_class = self.get_state(s, "device_class")
                
                #remap state text if mapping exists
                if "state_mapping" in self.args["alarm"].keys():
                    if this_sensor_device_class in self.args["alarm"]["state_mapping"]:
                        if this_sensor_state in self.args["alarm"]["state_mapping"][this_sensor_device_class].keys():
                            this_sensor_state = self.args["alarm"]["state_mapping"][this_sensor_device_class][this_sensor_state]
                msg += "{}: {}\n".format(this_sensor_name, this_sensor_state)
        return msg
    
    #setup for changing alarm state. Prompts user for pin
    def alarm_set(self, user_id, user_name, args):
        self.pending_alarm_state = None
        msg = "Unknown alarm state"
        if len(args) == 1:
            if args[0] in ALARM_STATES:
                self.pending_alarm_state = args[0]
                self.receiving_alarm_pin = True
                msg = "Enter alarm pin"
        return msg, None
    
    #calls service to change alarm state
    def action_alarm_pin(pin):
        msg = "Pin is incorrect"
        if isinstance(pin, six.string_types) and  len(pin) < 12 and pin.isalnum():
            #get values for service call
            alarm_instance = self.args["alarm"]["control"]
            alarm_control_parent = alarm_instance.split('.')[0]
            
            #call alarm set service
            service_name = "{}/{}".format(alarm_control_parent, ALARM_SERVICES[ALARM_STATES.index(self.pending_alarm_state)])
            self.call_service(service_name, entity_id = alarm_instance, code=pin)
            
            #check that something happened
            alarm_state = self.get_state(self.args["alarm"]["control"])
            if alarm_state == self.pending_alarm_state:
                msg = "Alarm state changed"
        self.pending_alarm_state = None
        return msg 
        
    #prints current temperatures
    def temps_command(self, user_id, user_name, args):
        temp_group = self.get_state(self.args["temp_group"], "entity_id")
        
        msg = "Temperatures: \n"
        for t in temp_group:
            this_temp_name = self.get_state(t, "friendly_name")
            this_temp_temp = self.get_state(t)
            this_temp_units = self.get_state(t, "unit_of_measurement")
            msg += "{}: {}{}\n".format(this_temp_name, this_temp_temp, this_temp_units)
        
        return msg, None

    #telegram command received
    def receive_telegram_command(self, event_id, payload_event, *args):
        assert event_id == 'telegram_command'
        user_id = payload_event['user_id']
        command = payload_event['command']
        user_name = payload_event['from_first']
        cmd_args = []
        
        if(' ' in command):
            cmd_bits = command.split(' ')
            command = cmd_bits[0]
            cmd_args = cmd_bits[1:]

        ret, msg, keyboard = self.process_commands(command, user_id, user_name, cmd_args) 
        if ret:
            self.call_service(
                'telegram_bot/send_message',
                target=user_id,
                message=msg,
                disable_notification=True,
                inline_keyboard=keyboard)

    #response to previous message
    def receive_telegram_callback(self, event_id, payload_event, *args):
        assert event_id == 'telegram_callback'
        user_id = payload_event['user_id']
        user_name = payload_event['from_first']
        data_callback = payload_event['data']
        callback_id = payload_event['id']
        cmd_args = []
        
        if(' ' in data_callback):
            cmd_bits = data_callback.split(' ')
            data_callback = cmd_bits[0]
            cmd_args = cmd_bits[1:]
        
        #send_messaage is for chat window replies, answer_callback_query is for banner notification type responses
        
        ret, msg, keyboard = self.process_commands(data_callback, user_id, user_name, cmd_args)
        if ret:
            self.call_service(
                'telegram_bot/send_message',
                target=user_id,
                message=msg,
                disable_notification=True,
                inline_keyboard=keyboard)
        else:
            ret, msg, keyboard = self.process_callback_only_commands(data_callback, user_id, user_name)
            if ret:
                self.call_service(
                    'telegram_bot/answer_callback_query',
                    message=msg,
                    callback_query_id=callback_id)

    #Non-command, non-callback response, regular text
    def receive_telegram_text(self, event_id, payload_event, *args):
        user_id = payload_event['user_id']
        user_name = payload_event['from_first']
        query_text = payload_event["text"]
        msg_id = payload_event["id"]
        chat_id = payload_event["chat_id"]
        
        #check for alarm pin sent at prompt
        if self.receiving_alarm_pin:
            msg = self.action_alarm_pin(query_text)
            
            #delete message for security
            self.call_service(
                "telegram_bot/edit_message",
                chat_id=chat_id,
                message_id=msg_id,
                message="******",
                inline_keyboard=None
            )
            
            #send response
            self.call_service(
                'telegram_bot/send_message',
                target=user_id,
                message=msg,
                disable_notification=True,
                inline_keyboard=None)
                    
            self.receiving_alarm_pin = False
            
        #regular message/enquiry
        else:
            #received question or random message
            msg = "Sorry, I didn't understand that."
            self.call_service(
                'telegram_bot/send_message',
                target=user_id,
                message=msg,
                disable_notification=True,
                inline_keyboard=None)