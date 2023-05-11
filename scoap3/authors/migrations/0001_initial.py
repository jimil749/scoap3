# Generated by Django 4.2 on 2023-05-16 14:46

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("articles", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="Author",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("first_name", models.CharField(max_length=255)),
                ("last_name", models.CharField(max_length=255)),
                ("email", models.EmailField(max_length=254)),
                ("author_order", models.IntegerField(blank=True)),
                (
                    "article_id",
                    models.ForeignKey(
                        blank=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        to="articles.article",
                    ),
                ),
            ],
            options={
                "ordering": ["id"],
            },
        ),
        migrations.CreateModel(
            name="AuthorIdentifier",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "identifier_type",
                    models.CharField(choices=[("ORCID", "Orcid")], max_length=255),
                ),
                ("identifier_value", models.CharField(max_length=255)),
                (
                    "author_id",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE, to="authors.author"
                    ),
                ),
            ],
            options={
                "ordering": ["id"],
            },
        ),
        migrations.AddIndex(
            model_name="authoridentifier",
            index=models.Index(
                fields=["author_id", "identifier_type", "identifier_value"],
                name="authors_aut_author__2927b2_idx",
            ),
        ),
    ]