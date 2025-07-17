# reservas/urls.py
from django.urls import path
from . import views

app_name = 'reservas'

urlpatterns = [
    # URLs para reservas (unificada para clientes y empleados)
    path('crear/<int:maquinaria_id>/', views.crear_reserva, name='crear_reserva'),
    path('confirmar-reservas/', views.confirmar_reservas, name='confirmar_reservas'),
    path('confirmar-reserva-cliente/', views.confirmar_reserva_cliente, name='confirmar_reserva_cliente'),
    path('get-sucursales-disponibles/', views.get_sucursales_disponibles, name='get_sucursales_disponibles'),
    
    # URL para historial de reservas (unificada para todos los usuarios)
    path('historial/', views.lista_reservas, name='lista_reservas'),
    
    # URLs compartidas
    path('detalle/<int:reserva_id>/', views.detalle_reserva, name='detalle_reserva'),
    path('cancelar/<int:reserva_id>/', views.cancelar_reserva, name='cancelar_reserva'),
    path('reembolsar/<int:reserva_id>/', views.reembolsar_reserva, name='reembolsar_reserva'),
    path('reserva-cancelada/<int:reserva_id>/', views.reserva_cancelada, name='reserva_cancelada'),
    
    # URLs para empleados
    path('procesar-reservas/', views.procesar_reservas, name='procesar_reservas'),
    path('finalizar-por-codigo/', views.finalizar_reserva_por_codigo, name='finalizar_reserva_por_codigo'),
    path('entregar-por-codigo/', views.entregar_reserva_por_codigo, name='entregar_reserva_por_codigo'),
    path('devolucion/<int:reserva_id>/', views.devolucion_reserva, name='devolucion_reserva'),
    path('confirmar-devolucion/<int:reserva_id>/', views.confirmar_devolucion, name='confirmar_devolucion'),
    
    # URLs para verificación AJAX
    path('verificar-disponibilidad/', views.verificar_disponibilidad_ajax, name='verificar_disponibilidad_ajax'),
    
    # URLs para pagos
    path('procesar-pago/<int:reserva_id>/', views.procesar_pago, name='procesar_pago'),
    path('aplicar-cupon/<int:reserva_id>/', views.aplicar_cupon_view, name='aplicar_cupon'),
    path('payment/success/<int:reserva_id>/', views.payment_success, name='payment_success'),
    path('payment/failure/<int:reserva_id>/', views.payment_failure, name='payment_failure'),
    path('payment/pending/<int:reserva_id>/', views.payment_pending, name='payment_pending'),
    path('payment/webhook/', views.payment_webhook, name='payment_webhook'),
    path('mostrar-qr/<int:reserva_id>/', views.mostrar_qr_pago, name='mostrar_qr_pago'),
    
    # Nueva URL para verificar el estado de pago
    path('check-payment-status/<int:reserva_id>/', views.check_payment_status, name='check_payment_status'),
]