"""Switch ``MRPRun.mrp_calculation`` from CASCADE to PROTECT.

D-05 fix from [.claude/reviews/mrp-sqa-review.md](../../../.claude/reviews/mrp-sqa-review.md):
deleting an MRPCalculation that still has runs was silently destroying run
history. PROTECT surfaces an explicit error in the calc-delete view so
operators know to delete the runs first.
"""
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('mrp', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='mrprun',
            name='mrp_calculation',
            field=models.ForeignKey(
                help_text=(
                    'The working calculation snapshot this run produced. PROTECT '
                    'so deleting a calculation that still has runs surfaces an '
                    'explicit error rather than silently destroying run history.'
                ),
                on_delete=django.db.models.deletion.PROTECT,
                related_name='runs',
                to='mrp.mrpcalculation',
            ),
        ),
    ]
