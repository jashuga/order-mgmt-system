$(document).ready(function() {
    const table = $('#example').DataTable({
        ajax: {
            url: 'http://127.0.0.1:5000/orders',
            dataSrc: ''
        },
        columns: [
            { title: '<input type="checkbox" id="selectAll" aria-label="Select All Orders">', 
              data: null, 
              orderable: false, 
              render: function() { return '<input type="checkbox" class="selectOrder">'; }
            },
            { title: 'Time', data: 'time' },
            { title: 'Name', data: 'name' },
            { title: 'Phone', data: 'phone' },
            { title: 'Order', data: 'order_detail' },
            { title: 'Status', data: 'status' },
            { title: 'Quantity', data: 'quantity' },
            { title: 'Price (¥)', data: 'price', render: function(data) { return '¥' + data.toFixed(0); }},
            { title: 'Actions', data: null, defaultContent: `
                <button class="btn btn-sm btn-primary edit-order">Edit</button>
                <button class="btn btn-sm btn-danger delete-order">Delete</button>
            `}
        ],
        order: [[1, 'desc']]
    });

    $('#selectAll').on('click', function() {
        $('.selectOrder').prop('checked', this.checked);
    });

    $('#deleteSelected').on('click', function() {
        const selectedOrders = [];
        $('.selectOrder:checked').each(function() {
            const data = table.row($(this).parents('tr')).data();
            selectedOrders.push(data.id);
        });

        if (selectedOrders.length === 0) {
            alert("No orders selected.");
            return;
        }

        if (confirm(`Are you sure you want to delete ${selectedOrders.length} order(s)?`)) {
            selectedOrders.forEach(orderId => {
                $.ajax({
                    url: `http://127.0.0.1:5000/orders/${orderId}`,
                    type: 'DELETE',
                    success: function() {
                        table.ajax.reload();         
                    },
                    error: function() {
                        alert("Error deleting order.");
                    }
                });
            });
        }
    });

    $('#exportXlsx').on('click', function() {
        window.location.href = '/export_xlsx';
    });
    
    $('#exportCsv').on('click', function() {
        $.ajax({
            url: '/export_csv',
            type: 'GET',
            success: function(response) {
                const blob = new Blob([response], { type: 'text/csv;charset=utf-8;' });
                const link = document.createElement("a");
                link.href = URL.createObjectURL(blob);
                link.setAttribute("download", "orders_database.csv");
                document.body.appendChild(link);
                link.click();
                document.body.removeChild(link);
            },
            error: function() {
                alert("Error exporting database.");
            }
        });
    });
    
    $('#importCsv').on('click', function() {
        const file = $('#importFile')[0].files[0];
        if (!file) {
            alert("Please select a .csv file to import.");
            return;
        }
    
        const formData = new FormData();
        formData.append("file", file);
    
        $.ajax({
            url: '/import_csv',
            type: 'POST',
            data: formData,
            processData: false,
            contentType: false,
            success: function() {
                alert("Data imported successfully.");
                $('#example').DataTable().ajax.reload();
                $('#productTable').DataTable().ajax.reload();
            },
            error: function() {
                alert("Error importing data.");
            }
        });
    });

    $('#reminderForm').on('submit', function(e) {
        e.preventDefault();
        const manualTime = $('#manualTime').val();
        const autoReminder = $('#autoReminder').is(':checked');
    
        $.ajax({
            url: '/set_reminder',
            type: 'POST',
            contentType: 'application/json',
            data: JSON.stringify({ manual_time: manualTime, auto_reminder: autoReminder }),
            success: function(response) {
                alert("Reminder settings updated successfully.");
                $('#reminderModal').modal('hide');
            },
            error: function(xhr, status, error) {
                console.error("Failed to update reminder settings:", error);
                alert("Failed to update reminder settings. Please check console for details.");
            }
        });
    });

    const productTable = $('#productTable').DataTable({
        ajax: {
            url: 'http://127.0.0.1:5000/products',
            dataSrc: ''
        },
        columns: [
            { title: 'Name', data: 'name' },
            { title: 'Stock', data: 'stock' },
            { title: 'Price (¥)', data: 'price', render: function(data) { return '¥' + data.toFixed(0); }},
            { title: 'Actions', data: null, defaultContent: `
                <button class="btn btn-sm btn-primary edit-product">Edit</button>
                <button class="btn btn-sm btn-danger delete-product">Delete</button>
            `}
        ]
    });

    function loadProducts() {
        $.ajax({
            url: 'http://127.0.0.1:5000/products',
            type: 'GET',
            success: function(data) {
                $('#order').empty();
                data.forEach(product => {
                    $('#order').append(`<option value="${product.name}" data-price="${product.price}">${product.name}</option>`);
                });
            }
        });
    }

    loadProducts();

    $(document).ready(function() {
        $('#orderForm').on('submit', function(e) {
            e.preventDefault();
            
            const countryCode = $('#countryCode').val();
            const phoneInput = $('#phone').val().trim(); 
            const fullPhoneNumber = countryCode + phoneInput; 
    
            if (!/^\d{10}$/.test(phoneInput)) {
                alert("Phone number must be exactly 10 digits.");
                return;
            }

            const orderId = $('#orderId').val();
            const order = {
                time: new Date().toLocaleString(),
                name: $('#name').val(),
                phone: fullPhoneNumber,  
                order_detail: $('#order').val(),
                status: $('#status').val(),
                quantity: parseInt($('#quantity').val(), 10),
                price: parseFloat($('#order option:selected').data('price')) * parseInt($('#quantity').val(), 10)
            };
 
            const ajaxOptions = {
                url: orderId ? `http://127.0.0.1:5000/orders/${orderId}` : 'http://127.0.0.1:5000/orders',
                type: orderId ? 'PUT' : 'POST',
                contentType: 'application/json',
                data: JSON.stringify(order),
                success: function() {
                    table.ajax.reload();
                    $('#orderModal').modal('hide');
                    $('#orderForm')[0].reset();
                    loadProducts();
                },
                error: function(xhr) {
                    alert(xhr.responseJSON.error);
                }
            };
    
            $.ajax(ajaxOptions); 
        });
    
        $('#countryCode').on('change', function() {
        });
    });    
    
        
    $('#example tbody').on('click', '.edit-order', function() {
        const data = table.row($(this).parents('tr')).data();
        $('#orderId').val(data.id);
        $('#name').val(data.name);
        $('#phone').val(data.phone);
        $('#order').val(data.order_detail);
        $('#status').val(data.status);
        $('#quantity').val(data.quantity);
        $('#orderModal').modal('show');
    });

    $('#example tbody').on('click', '.delete-order', function() {
        const data = table.row($(this).parents('tr')).data();
        const orderId = data.id;
    
        $.ajax({
            url: `http://127.0.0.1:5000/orders/${orderId}`,
            type: 'DELETE',
            success: function() {
                table.ajax.reload();         
                loadProducts();               
                productTable.ajax.reload();   
            }
        });
    });
        
    $('#selectAll').on('click', function() {
        $('.selectOrder').prop('checked', this.checked);
    });

    $('#deleteSelected').on('click', function() {
        const selectedOrders = [];
        $('.selectOrder:checked').each(function() {
            const data = table.row($(this).parents('tr')).data();
            selectedOrders.push(data.id);
        });

        selectedOrders.forEach(orderId => {
            $.ajax({
                url: `http://127.0.0.1:5000/orders/${orderId}`,
                type: 'DELETE',
                success: function() {
                    table.ajax.reload();
                }
            });
        });
    });

    $('#productForm').on('submit', function(e) {
        e.preventDefault();
        const productId = $('#productId').val();
        const product = {
            name: $('#productName').val(),
            stock: parseInt($('#productStock').val(), 10),
            price: parseFloat($('#productPrice').val())
        };

        const ajaxOptions = {
            url: productId ? `http://127.0.0.1:5000/products/${productId}` : 'http://127.0.0.1:5000/products',
            type: productId ? 'PUT' : 'POST',
            contentType: 'application/json',
            data: JSON.stringify(product),
            success: function() {
                productTable.ajax.reload();
    
                if ($('.alert-success').length === 0) {
                    $('#productForm').prepend('<div class="alert alert-success">Product saved successfully!</div>');
                }
                loadProducts();
            }
        };

        $.ajax(ajaxOptions);
    });

    $('#productTable tbody').on('click', '.edit-product', function() {
        const data = productTable.row($(this).parents('tr')).data();
        $('#productName').val(data.name);
        $('#productStock').val(data.stock);
        $('#productPrice').val(data.price);
        $('#productId').val(data.id); 
        $('#productModal').modal('show');
    });

    $('#productModal').on('hidden.bs.modal', function () {
        $('.alert-success').remove(); 
        $('#productForm')[0].reset(); 
    });

    $('#productTable tbody').on('click', '.delete-product', function() {
        const data = productTable.row($(this).parents('tr')).data();
        const productId = data.id;

        $.ajax({
            url: `http://127.0.0.1:5000/products/${productId}`,
            type: 'DELETE',
            success: function() {
                productTable.ajax.reload();
                loadProducts();
            }
        });
    });
});
