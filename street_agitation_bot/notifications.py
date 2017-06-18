
from street_agitation_bot import models


def notify_about_new_registration(bot, region_id, agitator_id, text):
    region = models.Region.get_by_id(region_id)
    agitator = models.Agitator.find_by_id(agitator_id)
    bot.send_message(region.registrations_chat_it,
                     'Новая анкета\nРегион %s\n%s%s'
                     % (region.name, agitator.show_full(), text),
                     parse_mode="Markdown")


def notify_about_new_participant(bot, event_id, agitator_id):
    agitator = models.Agitator.find_by_id(agitator_id)
    event = (models.AgitationEvent.objects.filter(id=event_id)
             .select_related('place', 'place__region').first())
    region = event.place.region
    bot.send_message(region.registrations_chat_it,
                     'Новая заявка на участие\nРегион %s\nКуб %s\nВолонтер %s'
                     % (region.name, event.show(), agitator.show_full()),
                     parse_mode='Markdown')
