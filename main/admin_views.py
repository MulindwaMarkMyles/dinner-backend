from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.utils import timezone
from datetime import timedelta
from .models import User, DrinkType, DrinkTransaction, MealLog
from rest_framework.response import Response
from rest_framework import status

def is_admin(user):
    return user.is_staff or user.is_superuser

@login_required
@user_passes_test(is_admin)
def admin_dashboard(request):
    today = timezone.now().date()
    context = {
        'total_users': User.objects.count(),
        'total_drinks': DrinkType.objects.count(),
        'pending_orders_count': DrinkTransaction.objects.count(),
        'total_meals_today': MealLog.objects.filter(consumed_at__date=today).count(),
        'recent_orders': DrinkTransaction.objects.select_related('user', 'drink_type').order_by('-served_at')[:5],
        'low_stock_drinks': DrinkType.objects.filter(available_quantity__lt=50).order_by('available_quantity'),
        'current_time': timezone.now(),
    }
    return render(request, 'admin_dashboard.html', context)

@login_required
@user_passes_test(is_admin)
def admin_inventory(request):
    drinks = DrinkType.objects.all().order_by('-updated_at')
    return render(request, 'admin_inventory.html', {'drinks': drinks})

@login_required
@user_passes_test(is_admin)
def add_drink(request):
    if request.method == 'POST':
        name = request.POST.get('name')
        quantity = request.POST.get('quantity')
        DrinkType.objects.create(name=name, available_quantity=int(quantity))
        return redirect('admin_inventory')
    return redirect('admin_inventory')

@login_required
@user_passes_test(is_admin)
def edit_drink(request, drink_id):
    drink = get_object_or_404(DrinkType, id=drink_id)
    if request.method == 'POST':
        drink.name = request.POST.get('name', drink.name)
        drink.available_quantity = int(request.POST.get('quantity', drink.available_quantity))
        drink.save()
        return redirect('admin_inventory')
    return render(request, 'admin_inventory.html', {'edit_drink': drink})

@login_required
@user_passes_test(is_admin)
def delete_drink(request, drink_id):
    drink = get_object_or_404(DrinkType, id=drink_id)
    drink.delete()
    return redirect('admin_inventory')

@login_required
@user_passes_test(is_admin)
def admin_approvals(request):
    pending_orders = DrinkTransaction.objects.filter(status='pending').select_related('user', 'drink_type').order_by('-served_at')
    return render(request, 'admin_approvals.html', {'pending_orders': pending_orders})

@login_required
@user_passes_test(is_admin)
def approve_order(request, order_id):
    if request.method == 'POST':
        order = get_object_or_404(DrinkTransaction, id=order_id, status='pending')
        user = order.user
        drink_type = order.drink_type
        
        # Check if user still has drinks remaining
        if user.drinks_remaining < order.quantity:
            return Response({
                'error': f'User only has {user.drinks_remaining} drinks remaining'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Check if drink is still available
        if drink_type.available_quantity < order.quantity:
            return Response({
                'error': f'Only {drink_type.available_quantity} {drink_type.name} available'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Deduct from user allowance
        user.drinks_remaining -= order.quantity
        user.save()
        
        # Deduct from drink inventory
        drink_type.available_quantity -= order.quantity
        drink_type.save()
        
        # Update transaction status
        order.status = 'approved'
        order.approved_at = timezone.now()
        order.save()
        
        # Create meal log
        MealLog.objects.create(
            user=user,
            meal_type='drink',
            serving_point=order.serving_point
        )
        
    return redirect('admin_approvals')

@login_required
@user_passes_test(is_admin)
def deny_order(request, order_id):
    if request.method == 'POST':
        order = get_object_or_404(DrinkTransaction, id=order_id, status='pending')
        order.status = 'denied'
        order.approved_at = timezone.now()
        order.save()
    return redirect('admin_approvals')

@login_required
@user_passes_test(is_admin)
def admin_users(request):
    users = User.objects.all().order_by('-created_at')
    return render(request, 'admin_users.html', {'users': users})

@login_required
@user_passes_test(is_admin)
def edit_user(request, user_id):
    user = get_object_or_404(User, id=user_id)
    if request.method == 'POST':
        user.lunches_remaining = int(request.POST.get('lunches', user.lunches_remaining))
        user.dinners_remaining = int(request.POST.get('dinners', user.dinners_remaining))
        user.drinks_remaining = int(request.POST.get('drinks', user.drinks_remaining))
        user.save()
        return redirect('admin_users')
    return render(request, 'admin_users.html', {'edit_user': user})

@login_required
@user_passes_test(is_admin)
def delete_user(request, user_id):
    user = get_object_or_404(User, id=user_id)
    user.delete()
    return redirect('admin_users')

@login_required
@user_passes_test(is_admin)
def meal_logs(request):
    logs = MealLog.objects.select_related('user').order_by('-consumed_at')[:100]
    return render(request, 'admin_meal_logs.html', {'meal_logs': logs})
