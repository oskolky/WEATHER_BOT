from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import requests
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
import spacy
import sqlite3
import datetime
import geocoder
from db import init_db, save_history, get_history, get_last_city

app = FastAPI()

from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Ключи
OPENWEATHER_API_KEY = "0fabcf324e414b65ec2cfa8126b14bbf"
DEEPSEEK_API_KEY = "sk-647fe0aef85d47dbb352fdf6bce39441"

# API endpoints
WEATHER_URL = "https://api.openweathermap.org/data/2.5/weather"
FORECAST_URL = "https://api.openweathermap.org/data/2.5/forecast/daily"
DEEPSEEK_URL = "https://api.deepseek.com/v1/chat/completions"

# Загружаем модель SpaCy and SQLite
nlp = spacy.load("ru_core_news_sm")
init_db()

# Модель запроса от клиента
class TextRequest(BaseModel):
    text: str

# Модель ответа клиенту
class WeatherResponse(BaseModel):
    city: str
    temperature: float
    description: str
    advice: str 

# Извлечение города через SpaCy
def detect_location(text: str, user_id: str = "default"):
    # 1. Пытаемся найти город в текущем запросе
    doc = nlp(text)
    cities_in_text = [
        " ".join([token.lemma_ for token in ent])
        for ent in doc.ents
        if ent.label_ in ("LOC", "GPE")
    ]

    if cities_in_text:
        return cities_in_text[-1]  # Берем последний упомянутый город

    # 2. Если города нет в тексте - берем из истории
    last_city = get_last_city(user_id)
    if last_city:
        return last_city

    # 3. Фолбэк на геолокацию
    try:
        return geocoder.ip('me').city or "Минск"
    except:
        return "Минск"

def is_week_forecast_request(text: str) -> bool:
    doc = nlp(text.lower())
    for token in doc:
        if "недел" in token.lemma_:
            return True
    return False




# Получение фактической погоды
def fetch_weather(city: str):
    try:
        response = requests.get(
            f"{WEATHER_URL}?q={city}&appid={OPENWEATHER_API_KEY}&units=metric&lang=ru",
            timeout=10
        )
        if response.status_code != 200:
            return None

        data = response.json()
        return {
            "city": data["name"],
            "feels_like": data["main"]["feels_like"],
            "humidity": data["main"]["humidity"],
            "wind_speed": data["wind"]["speed"],
            "temperature": data["main"]["temp"],
            "description": data["weather"][0]["description"]
        }
    except Exception:
        return None


def get_coordinates(city: str):
    response = requests.get(
        f"https://api.openweathermap.org/data/2.5/weather?q={city}&appid={OPENWEATHER_API_KEY}&lang=ru",
        timeout=10
    )
    if response.status_code != 200:
        return None
    data = response.json()
    return data["coord"]["lat"], data["coord"]["lon"]

def fetch_weekly_forecast(city: str):
    coords = get_coordinates(city)
    if not coords:
        return None
    lat, lon = coords
    response = requests.get(
        f"https://api.openweathermap.org/data/3.0/onecall?lat={lat}&lon={lon}&exclude=current,minutely,hourly,alerts&units=metric&lang=ru&appid={OPENWEATHER_API_KEY}",
        timeout=10
    )
    if response.status_code != 200:
        return None
    data = response.json()
    forecast = []
    for day in data.get("daily", [])[:7]:
        forecast.append({
            "date": datetime.datetime.utcfromtimestamp(day["dt"]).strftime("%d.%m.%Y"),
            "temp_min": day["temp"]["min"],
            "temp_max": day["temp"]["max"],
            "description": day["weather"][0]["description"]
        })
    return forecast




# Генерация совета через DeepSeek API
def generate_weather_advice(weather_data, user_input):
    headers = {
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
        "Content-Type": "application/json"
    }
    system_prompt = "Ты дружелюбный погодный помощник. Дай совет человеку."
    user_prompt = (
        f"Пользователь спросил: \"{user_input}\"\n\n"
        f"Температура: {weather_data['temperature']}°C. "
        f"Ощущается как: {weather_data['feels_like']}°C. "
        f"Влажность: {weather_data['humidity']}%. "
        f"Скорость ветра: {weather_data['wind_speed']} м/с. "
        f"Описание: {weather_data['description']}."
    )

    payload = {
        "model": "deepseek-chat",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        "temperature": 0.7,
        "max_tokens": 300
    }

    try:
        response = requests.post(DEEPSEEK_URL, headers=headers, json=payload, timeout=45)
        response.raise_for_status()
        data = response.json()
        return data["choices"][0]["message"]["content"]
    except Exception as e:
        print(f"Ошибка запроса к DeepSeek: {e}")
        return "Не удалось получить совет по погоде."

def generate_weekly_advice(forecast_data, user_input):
    headers = {
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
        "Content-Type": "application/json"
    }
    system_prompt = "Ты дружелюбный погодный помощник. Дай совет человеку на основе прогноза погоды на неделю."
    forecast_text = "\n".join([
        f"{day['date']}: от {day['temp_min']}°C до {day['temp_max']}°C, {day['description']}"
        for day in forecast_data
    ])
    user_prompt = (
        f"Пользователь спросил: \"{user_input}\"\n\n"
        f"Прогноз на неделю:\n{forecast_text}"
    )
    payload = {
        "model": "deepseek-chat",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        "temperature": 0.7,
        "max_tokens": 300
    }
    try:
        response = requests.post(DEEPSEEK_URL, headers=headers, json=payload, timeout=45)
        response.raise_for_status()
        data = response.json()
        return data["choices"][0]["message"]["content"]
    except Exception as e:
        print(f"Ошибка запроса к DeepSeek: {e}")
        return "Не удалось получить совет по прогнозу на неделю."



# Основной эндпоинт
@app.post("/weather-from-text/", response_model=WeatherResponse)
async def get_weather_from_text(request: TextRequest):
    us_id = "default"
    city = detect_location(request.text)
    if not city:
        raise HTTPException(status_code=400, detail="City not found in text")
    if is_week_forecast_request(request.text):
        forecast_data = fetch_weekly_forecast(city)
        if not forecast_data:
            raise HTTPException(status_code=404, detail="Weekly forecast not available")
        advice = generate_weekly_advice(forecast_data, request.text)
        save_history(user_id=us_id, user_input=request.text, city=city, advice=advice)
        return WeatherResponse(
            city=city,
            temperature=forecast_data[0]["temp_max"],
            description=forecast_data[0]["description"],
            advice=advice
        )
    else:
        weather_data = fetch_weather(city)
        if not weather_data:
            raise HTTPException(status_code=404, detail="Weather data not available")
        advice = generate_weather_advice(weather_data, request.text)
        save_history(user_id=us_id, user_input=request.text, city=city, advice=advice)
        return WeatherResponse(
            city=weather_data["city"],
            temperature=weather_data["temperature"],
            description=weather_data["description"],
            advice=advice
        )



@app.get("/history/")
def history():
    return JSONResponse(content=get_history())

@app.get("/debug/history")
async def debug_history():
    try:
        conn = sqlite3.connect('weather.db')
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM history ORDER BY timestamp DESC")
        rows = cursor.fetchall()
        return {
            "count": len(rows),
            "items": [dict(zip([column[0] for column in cursor.description], row)) for row in rows]
        }
    finally:
        if conn:
            conn.close()

app.mount("/", StaticFiles(directory="../frontend", html=True), name="frontend")


