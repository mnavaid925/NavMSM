from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('plm', '0003_product_cost_center'),
    ]

    operations = [
        migrations.AddField(
            model_name='product',
            name='standard_sale_price',
            field=models.DecimalField(
                blank=True,
                decimal_places=4,
                help_text='Placeholder unit sale price for gross-margin reports until Module 17 (Sales) ships.',
                max_digits=14,
                null=True,
            ),
        ),
    ]
