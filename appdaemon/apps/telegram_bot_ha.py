import appdaemon.plugins.hass.hassapi as hass
import pprint

class TelegramBotEventListener(hass.Hass):
    """Event listener for Telegram bot events."""

    def initialize(self):
        #config validation
        self.aircon_configured = False
        self.alarm_configured = False
        self.temperature_configured = False
        if "aircon" in self.args.keys():
            self.aircon_configured = True
        if "alarm" in self.args.keys():
            self.alarm_configured = True
        if "temp_group" in self.args.keys():
            self.temperature_configured = True
            
        #initial states
        self.receiving_alarm_pin = False
    
        """Listen to Telegram Bot events of interest."""
        self.listen_event(self.receive_telegram_command, 'telegram_command')
        self.listen_event(self.receive_telegram_callback, 'telegram_callback')
        self.listen_event(self.receive_telegram_text, "telegram_text")
        
    def process_commands(self, command, user_id, user_name):
        ret = True
        msg = None
        keyboard = None
        
        if command == "/hello" or command == "/help":
            msg, keyboard = self.hello_command(user_id, user_name)
        elif command == "/aircon" and self.aircon_configured:
            msg, keyboard = self.aircon_command(user_id, user_name)
        elif command == "/alarm" and self.alarm_configured:
            msg, keyboard = self.alarm_command(user_id, user_name)
        elif command == "/temps" and self.temperature_configured:
            msg, keyboard = self.temps_command(user_id, user_name)
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

    def hello_command(self, user_id, user_name):
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
            
    def aircon_command(self, user_id, user_name):
        aircon_state = self.get_state(self.args["aircon"])
        aircon_current_temp = self.get_state(self.args["aircon"], 'current_temperature')
        aircon_setpoint_temp = self.get_state(self.args["aircon"], 'temperature')
        
        msg = "Airconditioner is currently set to {}. Current temperature is {} degrees.".format(aircon_state, aircon_current_temp)
        if aircon_state in ["cool", "heat", "heat_cool"]:
            msg += "Setpoint is {} degrees".format(aircon_setpoint_temp)
              
        keyboard = [[("Off", "/aircon_set off"), ("Fan", "/aircon_set fan"), ("Cool", "/aircon_set cool")],
                    [("Heat", "/aircon_set heat"), ("Goodbye", "/do_nothing")]]
                                                    
        return msg, keyboard
            
    def alarm_command(self, user_id, user_name):
        alarm_state = self.get_state(self.args["alarm"])
        
        msg = "Alarm is currently {}".format(str(alarm_state).replace("_", " "))

        keyboard = [[("Disarm", "/alarm_set disarm"), ("Arm Night", "/alarm_set arm_night")],
                    [("Arm Away", "/alarm_set arm_away"), ("Goodbye", "/do_nothing")]]
                    
        return msg, keyboard
        
    def alarm_set(self, user_id, user_name):
        self.pending_alarm_state = None
        
    def action_alarm_pin(pin):
        pass
            
    def temps_command(self, user_id, user_name):
        msg = "Temps"
        
        return msg, None

    def receive_telegram_command(self, event_id, payload_event, *args):
        assert event_id == 'telegram_command'
        user_id = payload_event['user_id']
        command = payload_event['command']
        user_name = payload_event['from_first']

        ret, msg, keyboard = self.process_commands(command, user_id, user_name)
        if ret:
            self.call_service(
                'telegram_bot/send_message',
                target=user_id,
                message=msg,
                disable_notification=True,
                inline_keyboard=keyboard)

    def receive_telegram_callback(self, event_id, payload_event, *args):
        assert event_id == 'telegram_callback'
        user_id = payload_event['user_id']
        user_name = payload_event['from_first']
        data_callback = payload_event['data']
        callback_id = payload_event['id']
        
        #send_messaage is for chat window replies, answer_callback_query is for banner notification type responses
        
        ret, msg, keyboard = self.process_commands(data_callback, user_id, user_name)
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

    def receive_telegram_text(self, event_id, payload_event, *args):
        user_id = payload_event['user_id']
        user_name = payload_event['from_first']
        query_text = payload_event["text"]
        msg_id = payload_event["id"]
        chat_id = payload_event["chat_id"]
        
        if self.receiving_alarm_pin:
            self.action_alarm_pin(query_text)
            
            #delete message for security
            self.call_service(
                "telegram_bot/edit_message",
                chat_id=chat_id,
                message_id=msg_id,
                message="******",
                inline_keyboard=None
            )
            self.receiving_alarm_pin = False
        else:
            #received question or random message
            msg = "Sorry, I didn't understand that."
            self.call_service(
                'telegram_bot/send_message',
                target=user_id,
                message=msg,
                disable_notification=True,
                inline_keyboard=None)