from django.core.management.base import BaseCommand, CommandError
import logging
import math

from telegram import (ReplyKeyboardMarkup, ReplyKeyboardRemove, ParseMode)
from telegram.ext import (Updater, CommandHandler, MessageHandler, Filters,
                          ConversationHandler)

from recipefinder.models import IngredientCategory, Ingredient
from recipefinder.utils.util_rank import rank_recipes

# Enable logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    level=logging.INFO)

logger = logging.getLogger(__name__)

MAIN, CATEGORY, INGREDIENT = range(3)

def split_array(array, size_per_list):
    new_array = []
    for i in range(math.ceil(len(array) / size_per_list)):
        new_array.append(array[i * size_per_list: min((i + 1) * size_per_list, len(array))])
    return new_array

def get_categories():
    return list(map(capitalize_sentence, IngredientCategory.objects.all().values_list('name', flat=True)))

def get_ingredients(category_name):
    return list(map(capitalize_sentence, Ingredient.objects.filter(category__name=category_name).values_list('name', flat=True)))

def capitalize_sentence(sentence):
    return " ".join(w.capitalize() for w in sentence.split())

class Command(BaseCommand):
    help = 'Closes the specified poll for voting'

    def __init__(self):
        self.data = {}

    def handle(self, *args, **options):
        # TODO: change
        self.main()

    def get_category_keyboard(self):
        return split_array(get_categories(), 3)

    def get_ingredient_keyboard(self, category_names):
        return split_array(get_ingredients(category_names), 3)

    def update_current_status(self, update):
        user = update.message.from_user
        ingredients = self.data[user.id]["ingredients"]

        update.message.reply_text(
            'Current Ingredients:\n' + "\n".join(ingredients) + "\n\n"
            'Send /add to add more ingredients.\n'
            'Send /done to find your recipes.\n'
            'Send /cancel to stop talking to me.\n')


    def reset_status(self, update):
        user = update.message.from_user

        self.data[user.id] = {
            "ingredients": []
        }


    def start(self, update, context):
        self.reset_status(update)

        update.message.reply_text('Hi! My name is buttercream frosting Bot. '
            'Select the ingredients you have in your fridge and '
            'I will help you decide on what delicious meals you can prepare with them')
            
        self.update_current_status(update)

        return MAIN

    def add(self, update, context):
        user = update.message.from_user

        update.message.reply_text(
            'Select a category of ingredients',
            reply_markup=ReplyKeyboardMarkup(self.get_category_keyboard(), one_time_keyboard=True))

        return CATEGORY


    def category(self, update, context):
        user = update.message.from_user
        category = update.message.text

        if not category in get_categories():
            return CATEGORY

        self.data[user.id]["category"] = category

        update.message.reply_text('Choose the ingredient you want to add.',
                                reply_markup=ReplyKeyboardMarkup(self.get_ingredient_keyboard(category), one_time_keyboard=True))

        return INGREDIENT

    def ingredient(self, update, context):
        user = update.message.from_user
        ingredient = update.message.text
        category = self.data[user.id]["category"]

        if not ingredient in get_ingredients(category):
            return INGREDIENT

        ingredients = self.data[user.id]["ingredients"]
        ingredients.append(ingredient)

        update.message.reply_text('The ingredient ' + ingredient + ' has been added.')

        self.update_current_status(update)
        return MAIN

    def status(self, update, context):
        self.update_current_status(update)
        return MAIN

    def done(self, update, context):
        user = update.message.from_user

        ingredients = self.data[user.id]["ingredients"]

        ingredients_list = Ingredient.objects.filter(name__in=ingredients)

        result = ""
        recipes = rank_recipes(ingredients_list, n=5)

        ingredients_name_list = set(map(capitalize_sentence, ingredients_list.values_list("name", flat=True)))

        for i, (point, recipe) in enumerate(recipes):
            all_ingredients = set(map(capitalize_sentence, recipe.ingredients.get_queryset().values_list("name", flat=True)))
            have_ingredients = all_ingredients & ingredients_name_list
            missing_ingredients = all_ingredients - ingredients_name_list
            result += str(i + 1) + "\n"
            result += "Name: " + capitalize_sentence(recipe.name) + "\n"
            result += "Similarity Point: " + "{:.1%}".format(point) + "\n"
            result += "Ingredients: " + "<b>" + ", ".join(have_ingredients) + "</b>" + (", " if len(missing_ingredients) > 0 and len(have_ingredients) > 0 else "") + (("<i>" + ", ".join(missing_ingredients) + "</i>") if len(missing_ingredients) > 0 else "")+ "\n"
            result += "Website: " + recipe.recipe_link + "\n"
            result += "\n"

        update.message.reply_text(result, parse_mode=ParseMode.HTML)

        return MAIN

    def cancel(self, update, context):
        user = update.message.from_user
        logger.info("User %s canceled the conversation.", user.first_name)
        update.message.reply_text('Bye! I hope we can talk again some day.',
                                reply_markup=ReplyKeyboardRemove())

        return ConversationHandler.END


    def error(self, update, context):
        """Log Errors caused by Updates."""
        logger.warning('Update "%s" caused error "%s"', update, context.error)


    def main(self):
        updater = Updater(
            "1002329449:AAFAK5ltD_lg-g8MAc9iC-0KaK12qZDfEqk", use_context=True)

        # Get the dispatcher to register handlers
        dp = updater.dispatcher

        conv_handler = ConversationHandler(
            entry_points=[CommandHandler('start', self.start)],

            states={
                MAIN: [CommandHandler('add', self.add),
                        CommandHandler('done', self.done),
                        CommandHandler('status', self.status)],

                CATEGORY: [MessageHandler(Filters.text, self.category)],

                INGREDIENT: [MessageHandler(Filters.text, self.ingredient)]
            },

            fallbacks=[CommandHandler('cancel', self.cancel)]
        )

        dp.add_handler(conv_handler)

        # log all errors
        dp.add_error_handler(self.error)

        # Start the Bot
        updater.start_polling()

        # Run the bot until you press Ctrl-C or the process receives SIGINT,
        # SIGTERM or SIGABRT. This should be used most of the time, since
        # start_polling() is non-blocking and will stop the bot gracefully.
        updater.idle()