from aiogram.fsm.state import State, StatesGroup


class ProfileForm(StatesGroup):
    gender = State()
    height = State()
    weight = State()
    age = State()
    activity = State()


class AnalysisFlow(StatesGroup):
    waiting_photo = State()
