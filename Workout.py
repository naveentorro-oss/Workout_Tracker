from google import genai
from google.genai import types
from pydantic import BaseModel
from st_supabase_connection import SupabaseConnection, execute_query
import streamlit as st


GEMINI_MODEL = "gemini-3.8-flash"


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

try:
    gemini_api_key = st.secrets.get("GEMINI_API_KEY")
    ai_client = genai.Client(api_key=gemini_api_key) if gemini_api_key else None
except Exception:
    ai_client = None

try:
    db_conn = st.connection("supabase", type=SupabaseConnection)
except Exception:
    db_conn = None


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


def get_saved_rows(result):
    if result is None:
        return []
    if hasattr(result, "data"):
        return result.data or []
    if isinstance(result, dict):
        return result.get("data") or []
    if isinstance(result, list):
        return result
    return []


# 4. Generate & Save Workout
if st.button("Generate Workout"):
    if ai_client is None:
        st.error("GEMINI_API_KEY is missing or invalid. Check your Streamlit secrets.")
    else:
        prompt = (
            f"Create a {duration}-minute {goal} workout using only:"
            f" {', '.join(equipment)}."
        )

        try:
            with st.spinner("Generating structured routine..."):
                response = ai_client.models.generate_content(
                    model=GEMINI_MODEL,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        response_schema=WorkoutPlan,
                    ),
                )

            if response.parsed is None:
                st.error("The AI model returned no workout plan.")
            else:
                st.session_state["current_plan"] = response.parsed
        except Exception as exc:
            st.error(f"Workout generation failed: {exc}")

if "current_plan" in st.session_state:
    plan = st.session_state["current_plan"]
    st.subheader(plan.plan_title)
    st.caption(f"Focus: {', '.join(plan.target_muscles)}")
    st.dataframe([ex.model_dump() for ex in plan.exercises])

    if st.button("Save Plan to Cloud"):
        if db_conn is None:
            st.error("Supabase connection is not configured. Check your Streamlit connection settings.")
        else:
            try:
                execute_query(
                    db_conn.table("workout_plans").insert({
                        "goal": goal,
                        "workout_json": plan.model_dump(),
                    }),
                    ttl=0,
                )
                st.success("Saved to Supabase!")
            except Exception as exc:
                st.error(f"Unable to save workout: {exc}")

# 5. View Saved Cloud History
st.divider()
st.subheader("☁️ Saved Cloud Workouts")

if db_conn is not None:
    try:
        saved_data = execute_query(
            db_conn.table("workout_plans")
            .select("*")
            .order("created_at", desc=True)
            .limit(5),
            ttl=0,
        )
        saved_rows = get_saved_rows(saved_data)

        if saved_rows:
            for row in saved_rows:
                workout_json = row.get("workout_json") or {}
                title = workout_json.get("plan_title", "Untitled workout")
                created_at = str(row.get("created_at") or "")[:10]
                with st.expander(f"{title} ({created_at})"):
                    st.dataframe(workout_json.get("exercises", []))
        else:
            st.info("No saved workouts yet.")
    except Exception as exc:
        st.error(f"Unable to load workout history: {exc}")
else:
    st.info("Connect Supabase to view saved workouts.")
