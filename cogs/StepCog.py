import pandas as pd
import discord
from discord import app_commands
from discord.ext import commands
from io import BytesIO
import datetime as dt


class ProcessedResult:
    def __init__(self, total_steps, average_steps, num_of_missing_data, num_of_people_missing):
        self.total_steps = total_steps
        self.average_steps = average_steps
        self.num_of_missing_data = num_of_missing_data
        self.num_of_people_missing = num_of_people_missing


def process_report(data_frame: pd.DataFrame) -> str:
    total_steps = data_frame["Total Steps"].sum(numeric_only=True)
    average_steps = data_frame["Avg Daily Steps"].mean(numeric_only=True)

    current_week_start, current_week_end = get_formatted_date(7), get_formatted_date(1)
    current_week = calculate_time_slice(data_frame, current_week_start, current_week_end)
    previous_week = calculate_time_slice(data_frame, get_formatted_date(14), get_formatted_date(8))

    report = f"""Walking Report ({current_week_start} to {current_week_end}):
- {int(current_week.total_steps)} total steps ({int(current_week.total_steps - previous_week.total_steps):+} steps)
- This is {steps_to_km(current_week.total_steps)} kilometers!
- {current_week.average_steps.round(2)} average steps per person per day ({(current_week.average_steps - previous_week.average_steps).round(2):+} steps)
- This is an average of {steps_to_km(current_week.average_steps)} kilometers a day!"""

    if current_week.num_of_missing_data != 0:
        report += f"""
- Note: There are {current_week.num_of_missing_data} entries missing across {current_week.num_of_people_missing} people"""

    report += f""" 

Therefore, as of {current_week_end}:
- Total step count: {int(total_steps)}
- Total distance (km): {steps_to_km(total_steps)}
- Average step count: {average_steps.round(2)}"""

    return report


def steps_to_km(steps: int, stride_length_m: float = 0.762) -> float:
    distance_km = (steps * stride_length_m) / 1000
    return round(distance_km, 2)


def calculate_time_slice(data_frame: pd.DataFrame, from_time: str, to_time: str):
    # Both are formated as "YYYY-MM-DD"
    slice = data_frame.loc[:, from_time:to_time]
    total_steps = slice.sum(axis=None, numeric_only=True)
    average_steps = slice.mean(axis=None, numeric_only=True)
    num_of_missing_data = slice.isnull().values.ravel().sum()
    num_of_people_missing = slice.isnull().any(axis=1).sum()

    return ProcessedResult(total_steps, average_steps, num_of_missing_data, num_of_people_missing)


def get_formatted_date(days_offset):
    date = dt.datetime.now() - dt.timedelta(days=days_offset)
    return date.strftime("%Y-%m-%d")


class StepCog(commands.Cog):
    def __init__(self, bot):
        super().__init__()
        self.bot = bot

    @app_commands.command(description="Generates a Stepup report using a given csv")
    async def step_report(self, interaction, csv: discord.Attachment):
        if not csv.filename.endswith(".csv"):
            await interaction.response.send_message("Not a csv file")
            return

        try:
            bytes = csv.read()
            df = pd.read_csv(BytesIO(bytes), na_values=["N.A"])
            summary = process_report(df)
            await interaction.response.send_message(summary)
        except Exception as e:
            await interaction.response.send_message(f"Invalid csv file: {e}")


async def setup(bot):
    await bot.add_cog(StepCog(bot))
