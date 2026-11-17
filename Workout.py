from google import genai
from google.genai import types
from pydantic import BaseModel
from st_supabase_connection import SupabaseConnection, execute_query
import streamlit as st


# 1. Define Structured Output Schema
class Exercise(BaseModel):
  name: str
  sets: int
  reps: str
  rest_seconds: int


class WorkoutPlan(BaseModel):
  plan_title: str
  target_muscles: list[str]
  exercises: list[Exercise]


# 2. Initialize Clients
st.title("🤖 AI Workout Generator & Cloud Logger")
ai_client = genai.Client(api_key=st.secrets["GEMINI_API_KEY"])
db_conn = st.connection("supabase", type=SupabaseConnection)

# 3. User Inputs
goal = st.selectbox(
    "Fitness Goal", ["Hypertrophy", "Strength", "Fat Loss", "Endurance"]
)
equipment = st.multiselect(
    "Available Equipment",
    ["Dumbbells", "Barbell", "Pull-up Bar", "Bodyweight", "Kettlebell"],
    default=["Dumbbells", "Bodyweight"],
)
duration = st.slider("Duration (minutes)", 15, 90, 45)

# 4. Generate & Save Workout
if st.button("Generate Workout"):
  prompt = (
      f"Create a {duration}-minute {goal} workout using only:"
      f" {', '.join(equipment)}."
  )

  with st.spinner("Generating structured routine..."):
    response = ai_client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=WorkoutPlan,
        ),
    )
    st.session_state["current_plan"] = response.parsed

if "current_plan" in st.session_state:
  plan = st.session_state["current_plan"]
  st.subheader(plan.plan_title)
  st.caption(f"Focus: {', '.join(plan.target_muscles)}")
  st.dataframe([ex.model_dump() for ex in plan.exercises])

  if st.button("Save Plan to Cloud"):
    execute_query(
        db_conn.table("workout_plans").insert({
            "goal": goal,
            "workout_json": plan.model_dump(),
        }),
        ttl=0,
    )
    st.success("Saved to Supabase!")

# 5. View Saved Cloud History
st.divider()
st.subheader("☁️ Saved Cloud Workouts")
saved_data = execute_query(
    db_conn.table("workout_plans")
    .select("*")
    .order("created_at", desc=True)
    .limit(5),
    ttl=0,
)

if saved_data.data:
  for row in saved_data.data:
    with st.expander(
        f"{row['workout_json']['plan_title']} ({row['created_at'][:10]})"
    ):
      st.dataframe(row["workout_json"]["exercises"])