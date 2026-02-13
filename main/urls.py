from django.urls import path

from . import admin_views, views

urlpatterns = [
    path("main/api/lunch/", views.consume_lunch, name="consume_lunch"),
    path("main/api/dinner/", views.consume_dinner, name="consume_dinner"),
    path("main/api/drink/", views.consume_drink, name="consume_drink"),
    path("main/api/user/", views.get_user_status, name="get_user_status"),
    path("main/api/drinks/", views.list_drinks, name="list_drinks"),
    path("main/api/drinks/stock/", views.add_drink_stock, name="add_drink_stock"),
    path(
        "main/api/drinks/transactions/",
        views.drink_transactions,
        name="drink_transactions",
    ),
    path(
        "administrator/login/",
        admin_views.custom_admin_login,
        name="custom_admin_login",
    ),
    path(
        "administrator/logout/",
        admin_views.custom_admin_logout,
        name="custom_admin_logout",
    ),
    path("administrator/", admin_views.admin_dashboard, name="admin_dashboard"),
    path(
        "administrator/inventory/", admin_views.admin_inventory, name="admin_inventory"
    ),
    path("administrator/inventory/add/", admin_views.add_drink, name="add_drink"),
    path(
        "administrator/inventory/edit/<int:drink_id>/",
        admin_views.edit_drink,
        name="edit_drink",
    ),
    path(
        "administrator/inventory/delete/<int:drink_id>/",
        admin_views.delete_drink,
        name="delete_drink",
    ),
    path(
        "administrator/approvals/", admin_views.admin_approvals, name="admin_approvals"
    ),
    path(
        "administrator/approvals/approve/<int:order_id>/",
        admin_views.approve_order,
        name="approve_order",
    ),
    path(
        "administrator/approvals/deny/<int:order_id>/",
        admin_views.deny_order,
        name="deny_order",
    ),
    path("administrator/users/", admin_views.admin_users, name="admin_users"),
    path(
        "administrator/users/edit/<int:user_id>/",
        admin_views.edit_user,
        name="edit_user",
    ),
    path(
        "administrator/users/delete/<int:user_id>/",
        admin_views.delete_user,
        name="delete_user",
    ),
    path("administrator/logs/", admin_views.meal_logs, name="meal_logs"),
    path("administrator/chatbot/", admin_views.chatbot_view, name="chatbot_view"),
    path(
        "administrator/chatbot/conversation/",
        admin_views.chatbot_conversation,
        name="chatbot_new_conversation",
    ),
    path(
        "administrator/chatbot/conversation/<int:conversation_id>/",
        admin_views.chatbot_conversation,
        name="chatbot_conversation",
    ),
]
