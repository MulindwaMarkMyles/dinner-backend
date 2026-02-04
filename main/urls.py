from django.urls import path
from . import views

urlpatterns = [
    path('main/api/lunch/', views.consume_lunch, name='consume_lunch'),
    path('main/api/dinner/', views.consume_dinner, name='consume_dinner'),
    path('main/api/drink/', views.consume_drink, name='consume_drink'),
    path('main/api/user/', views.get_user_status, name='get_user_status'),
    path('main/api/drinks/', views.list_drinks, name='list_drinks'),
    path('main/api/drinks/stock/', views.add_drink_stock, name='add_drink_stock'),
    path('main/api/drinks/transactions/', views.drink_transactions, name='drink_transactions'),
]
