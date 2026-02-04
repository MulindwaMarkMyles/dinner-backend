from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
import random
from main.models import User, MealLog, DrinkType, DrinkTransaction

class Command(BaseCommand):
	help = "Populate the database with randomized users, meal logs, drink types, and drink transactions for testing."

	def add_arguments(self, parser):
		parser.add_argument("--users", type=int, default=5, help="Number of users to create.")
		parser.add_argument("--meal-logs-per-user", type=int, default=3, help="Meal logs per user.")
		parser.add_argument("--drink-transactions-per-user", type=int, default=4, help="Drink transactions per user.")
		parser.add_argument("--drink-types", type=int, default=3, help="Distinct drink types to seed.")

	def handle(self, *args, **options):
		first_names = ["Asha", "Brian", "Clara", "David", "Eve", "Fred"]
		last_names = ["Kato", "Mirembe", "Stone", "Odongo", "Mugisha", "Tembo"]
		genders = ["M", "F"]
		meal_points = ["Main Kitchen", "Annex", "Rooftop"]
		drink_locations = ["Bar", "Cafeteria", "Clubhouse"]

		users_to_create = options["users"]
		meal_logs_per_user = options["meal_logs_per_user"]
		drink_transactions_per_user = options["drink_transactions_per_user"]
		drink_types_count = options["drink_types"]

		DrinkType.objects.all().delete()
		MealLog.objects.all().delete()
		DrinkTransaction.objects.all().delete()

		drink_type_names = [
			"Sparkling Water",
			"Fresh Juice",
			"Craft Beer",
			"Iced Tea",
			"Cold Brew",
			"Herbal Soda",
		]
		selected_drink_types = random.sample(drink_type_names, min(drink_types_count, len(drink_type_names)))
		drink_types = []
		for name in selected_drink_types:
			obj, _ = DrinkType.objects.get_or_create(name=name)
			obj.available_quantity = random.randint(12, 40)
			obj.save()
			drink_types.append(obj)

		created_users = []
		used_keys = set()
		for _ in range(users_to_create):
			while True:
				first = random.choice(first_names)
				last = random.choice(last_names)
				gender = random.choice(genders)
				key = (first, last, gender)
				if key not in used_keys:
					used_keys.add(key)
					break
			allowances = User.default_allowances()
			user = User.objects.create(
				first_name=first,
				last_name=last,
				gender=gender,
				lunches_remaining=allowances["lunches"],
				dinners_remaining=allowances["dinners"],
				drinks_remaining=allowances["drinks"],
				week_start=timezone.now() - timedelta(days=random.randint(0, 6)),
			)
			created_users.append(user)

		for user in created_users:
			for _ in range(meal_logs_per_user):
				MealLog.objects.create(
					user=user,
					meal_type=random.choice([choice[0] for choice in MealLog.MEAL_TYPES]),
					consumed_at=timezone.now() - timedelta(days=random.randint(0, 6), seconds=random.randint(0, 86399)),
					serving_point=random.choice(meal_points),
				)
			for _ in range(drink_transactions_per_user):
				drink = random.choice(drink_types)
				quantity = random.randint(1, 3)
				drink.available_quantity = max(drink.available_quantity - quantity, 0)
				drink.save()
				DrinkTransaction.objects.create(
					user=user,
					drink_type=drink,
					quantity=quantity,
					serving_point=random.choice(drink_locations),
					served_at=timezone.now() - timedelta(days=random.randint(0, 6), seconds=random.randint(0, 86399)),
				)

		self.stdout.write(self.style.SUCCESS(f"Created {len(created_users)} users, "
			f"{len(created_users) * meal_logs_per_user} meal logs, "
			f"{len(created_users) * drink_transactions_per_user} drink transactions, "
			f"and {len(drink_types)} drink types."))
