"use strict";

/* =========================================================
   AIRVISION - COMPLETE FRONTEND JAVASCRIPT
   =========================================================
   Features:
   1. API and database connection status
   2. Dynamic city selection
   3. Historical air-quality data (up to 48 records)
   4. PM2.5 trend chart
   5. PM2.5 and PM10 cards
   6. Weather information: temperature, humidity, wind
   7. One-hour PM2.5 prediction
   8. Prediction comparison chart
   9. Model performance metrics
   10. Refresh functionality
   11. Error handling and debugging logs
========================================================= */


/* =========================================================
   1. CONFIGURATION
========================================================= */

const API_BASE_URL = "http://127.0.0.1:8000";

let pm25Chart = null;
let forecastChart = null;

let cities = [];
let currentRequestId = 0;


/* =========================================================
   2. DOM HELPERS
========================================================= */

function getElement(id) {
    return document.getElementById(id);
}


function setText(id, value) {
    const element = getElement(id);

    if (element) {
        element.textContent = value;
    }
}


function showError(message) {
    console.error("AirVision:", message);

    const element = getElement("error-message");

    if (element) {
        element.textContent = message;
        element.classList.remove("hidden");
    }
}


function clearError() {
    const element = getElement("error-message");

    if (element) {
        element.textContent = "";
        element.classList.add("hidden");
    }
}


function displayValue(value, suffix = "") {
    if (
        value === null ||
        value === undefined ||
        value === ""
    ) {
        return "--";
    }

    const number = Number(value);

    if (!Number.isFinite(number)) {
        return "--";
    }

    return `${Number(number.toFixed(2))}${suffix}`;
}


/* =========================================================
   3. API REQUEST HELPER
========================================================= */

async function apiRequest(path) {
    const url = `${API_BASE_URL}${path}`;

    console.log("AirVision API request:", url);

    const response = await fetch(url, {
        method: "GET",
        headers: {
            "Accept": "application/json"
        }
    });

    if (!response.ok) {
        let message = `Request failed: HTTP ${response.status}`;

        try {
            const errorData = await response.json();

            if (errorData.detail) {
                message = errorData.detail;
            }
        } catch (_) {
            // Keep the default error message.
        }

        throw new Error(message);
    }

    return await response.json();
}


/* =========================================================
   4. RESPONSE NORMALIZATION
========================================================= */

// Supports responses such as:
// [ {...}, {...} ]
// { "data": [ {...}, {...} ] }
// { "cities": [ {...}, {...} ] }

function extractArray(payload, possibleKeys = []) {
    if (Array.isArray(payload)) {
        return payload;
    }

    if (!payload || typeof payload !== "object") {
        return [];
    }

    for (const key of possibleKeys) {
        if (Array.isArray(payload[key])) {
            return payload[key];
        }
    }

    return [];
}


// Finds a field without being sensitive to capitalization.

function getField(record, possibleNames) {
    if (!record || typeof record !== "object") {
        return null;
    }

    for (const name of possibleNames) {
        const matchingKey = Object.keys(record).find(
            key => key.toLowerCase() === name.toLowerCase()
        );

        if (matchingKey !== undefined) {
            const value = record[matchingKey];

            if (value !== null && value !== undefined) {
                return value;
            }
        }
    }

    return null;
}


/* =========================================================
   5. STANDARDIZED FIELD ACCESSORS
========================================================= */

function getCityId(city) {
    return getField(city, [
        "city_id",
        "cityId",
        "id"
    ]);
}


function getCityName(city) {
    return getField(city, [
        "city_name",
        "cityName",
        "name",
        "city"
    ]);
}


function getTimestamp(record) {
    return getField(record, [
        "measured_at",
        "measuredAt",
        "observed_at",
        "observedAt",
        "timestamp",
        "datetime",
        "date",
        "time"
    ]);
}


function getPm25(record) {
    return getField(record, [
        "pm25",
        "pm2_5",
        "pm2.5",
        "pm25_value",
        "pm2_5_value",
        "pm_2_5"
    ]);
}


function getPm10(record) {
    return getField(record, [
        "pm10",
        "pm10_value"
    ]);
}


function getTemperature(record) {
    return getField(record, [
        "temperature_c",
        "temperature",
        "temp_c",
        "temp"
    ]);
}


function getHumidity(record) {
    return getField(record, [
        "humidity_pct",
        "humidity_percent",
        "relative_humidity",
        "relative_humidity_2m",
        "humidity"
    ]);
}


function getWindSpeed(record) {
    return getField(record, [
        "wind_speed_mps",
        "wind_speed",
        "windspeed",
        "wind_speed_kmh"
    ]);
}


/* =========================================================
   6. DATE AND TIME HELPERS
========================================================= */

function parseTimestamp(value) {
    if (!value) {
        return null;
    }

    const date = new Date(value);

    if (Number.isNaN(date.getTime())) {
        return null;
    }

    return date;
}


function formatTimestamp(value) {
    const date = parseTimestamp(value);

    if (!date) {
        return "--";
    }

    return date.toLocaleString();
}


function formatChartTimestamp(value) {
    const date = parseTimestamp(value);

    if (!date) {
        return "--";
    }

    return date.toLocaleString([], {
        day: "2-digit",
        month: "short",
        hour: "2-digit",
        minute: "2-digit"
    });
}


/* =========================================================
   7. LOAD AVAILABLE CITIES
========================================================= */

async function loadCities() {
    const payload = await apiRequest("/api/cities");

    console.log("AirVision cities API response:", payload);

    cities = extractArray(payload, [
        "cities",
        "data",
        "results"
    ]);

    const select = getElement("city-select");

    if (!select) {
        throw new Error(
            'HTML element with ID "city-select" was not found.'
        );
    }

    if (cities.length === 0) {
        throw new Error(
            "The cities API returned no city records."
        );
    }

    cities.sort((a, b) => {
        return String(getCityName(a) || "").localeCompare(
            String(getCityName(b) || "")
        );
    });

    select.replaceChildren();

    for (const city of cities) {
        const name = getCityName(city);

        if (!name) {
            continue;
        }

        const option = document.createElement("option");

        option.value = String(
            getCityId(city) ?? name
        );

        option.textContent = name;

        select.appendChild(option);
    }

    if (select.options.length === 0) {
        throw new Error(
            "No valid cities were found in the API response."
        );
    }

    // Set Delhi as the default city when available.

    const delhi = cities.find(city => {
        return String(getCityName(city)).toLowerCase() === "delhi";
    });

    const defaultCity = delhi || cities[0];

    select.value = String(
        getCityId(defaultCity) ?? getCityName(defaultCity)
    );

    console.log(
        "AirVision default city:",
        getCityName(defaultCity)
    );
}


/* =========================================================
   8. LOAD HISTORICAL AIR-QUALITY DATA
========================================================= */

async function loadAirQuality(city) {
    const cityName = getCityName(city);

    const path =
        `/api/air-quality/history` +
        `?city=${encodeURIComponent(cityName)}` +
        `&limit=48`;

    const payload = await apiRequest(path);

    console.log(
        "AirVision historical API response:",
        payload
    );

    let records = extractArray(payload, [
        "data",
        "records",
        "air_quality",
        "air_quality_records",
        "results"
    ]);

    console.log(
        "AirVision historical records received:",
        records.length
    );

    // Keep records for the selected city.

    records = records.filter(record => {
        const recordCity = getField(record, [
            "city_name",
            "cityName",
            "city"
        ]);

        if (recordCity === null) {
            return true;
        }

        return (
            String(recordCity).toLowerCase() ===
            String(cityName).toLowerCase()
        );
    });

    // Remove records without valid timestamps.

    records = records.filter(record => {
        return parseTimestamp(getTimestamp(record)) !== null;
    });

    // Sort from oldest to newest.

    records.sort((a, b) => {
        return (
            parseTimestamp(getTimestamp(a)).getTime() -
            parseTimestamp(getTimestamp(b)).getTime()
        );
    });

    console.log(
        `AirVision: ${records.length} valid historical records for ${cityName}.`
    );

    return records;
}


/* =========================================================
   9. LOAD WEATHER DATA
========================================================= */

async function loadWeather(city) {
    const cityName = getCityName(city);

    const path =
        `/api/weather/latest?city=${encodeURIComponent(cityName)}`;

    const payload = await apiRequest(path);

    console.log(
        "AirVision weather API response:",
        payload
    );

    // The API returns:
    // {
    //   "count": 1,
    //   "data": [
    //     {
    //       "city_name": "Delhi",
    //       "temperature_c": 21.4,
    //       "humidity_pct": 82.0,
    //       "wind_speed_mps": 1.0,
    //       "rain_mm": 0
    //     }
    //   ]
    // }

    let records = extractArray(payload, [
        "data",
        "records",
        "weather",
        "weather_data",
        "results"
    ]);

    // Also support a single weather record returned as an object.

    if (
        records.length === 0 &&
        payload &&
        typeof payload === "object" &&
        (
            getTemperature(payload) !== null ||
            getHumidity(payload) !== null
        )
    ) {
        records = [payload];
    }

    records = records.filter(record => {
        const recordCity = getField(record, [
            "city_name",
            "cityName",
            "city"
        ]);

        if (recordCity === null) {
            return true;
        }

        return (
            String(recordCity).toLowerCase() ===
            String(cityName).toLowerCase()
        );
    });

    records.sort((a, b) => {
        const dateA = parseTimestamp(getTimestamp(a));
        const dateB = parseTimestamp(getTimestamp(b));

        return (
            (dateA?.getTime() || 0) -
            (dateB?.getTime() || 0)
        );
    });

    console.log(
        `AirVision: ${records.length} weather record(s) for ${cityName}.`
    );

    return records;
}


/* =========================================================
   10. UPDATE AIR-QUALITY CARDS
========================================================= */

function updateAirQualityMetrics(records) {
    if (!Array.isArray(records)) {
        records = [];
    }

    const latest = records.length > 0
        ? records[records.length - 1]
        : null;

    console.log(
        "AirVision latest air-quality record:",
        latest
    );

    setText(
        "pm25-value",
        displayValue(latest ? getPm25(latest) : null)
    );

    setText(
        "pm10-value",
        displayValue(latest ? getPm10(latest) : null)
    );

    // Render the full historical dataset, not just the latest record.

    updatePm25Chart(records);
}


/* =========================================================
   11. UPDATE WEATHER CARDS
========================================================= */

function updateWeatherMetrics(records) {
    if (!Array.isArray(records)) {
        records = [];
    }

    const latest = records.length > 0
        ? records[records.length - 1]
        : null;

    console.log(
        "AirVision latest weather record:",
        latest
    );

    const temperature = latest
        ? getTemperature(latest)
        : null;

    const humidity = latest
        ? getHumidity(latest)
        : null;

    const wind = latest
        ? getWindSpeed(latest)
        : null;

    const timestamp = latest
        ? getTimestamp(latest)
        : null;

    // Main weather cards.

    setText(
        "temperature-value",
        displayValue(temperature)
    );

    setText(
        "humidity-value",
        displayValue(humidity)
    );

    // Additional weather information.

    setText(
        "weather-temperature",
        temperature === null
            ? "--"
            : `${displayValue(temperature)} °C`
    );

    setText(
        "weather-humidity",
        humidity === null
            ? "--"
            : `${displayValue(humidity)} %`
    );

    setText(
        "weather-wind",
        wind === null
            ? "--"
            : displayValue(wind)
    );

    setText(
        "weather-time",
        formatTimestamp(timestamp)
    );

    // Log the values being displayed.

    console.log("AirVision weather values:", {
        temperature,
        humidity,
        wind,
        timestamp
    });
}


/* =========================================================
   12. RENDER HISTORICAL PM2.5 CHART
========================================================= */

function updatePm25Chart(records) {
    const canvas = getElement("pm25-chart");
    const emptyMessage = getElement("chart-empty");

    if (!canvas) {
        console.error(
            'Chart canvas with ID "pm25-chart" was not found.'
        );

        return;
    }

    // Destroy the previous chart before rendering a new one.

    if (pm25Chart) {
        pm25Chart.destroy();
        pm25Chart = null;
    }

    if (typeof Chart === "undefined") {
        showError(
            "Chart.js could not load. Check your internet connection and HTML script imports."
        );

        return;
    }

    if (!Array.isArray(records)) {
        records = [];
    }

    // Keep only records with numeric PM2.5 values and valid timestamps.

    const validRecords = records.filter(record => {
        const value = getPm25(record);
        const timestamp = getTimestamp(record);

        return (
            value !== null &&
            value !== "" &&
            Number.isFinite(Number(value)) &&
            parseTimestamp(timestamp) !== null
        );
    });

    console.log(
        "AirVision chart valid records:",
        validRecords.length
    );

    if (validRecords.length === 0) {
        canvas.style.display = "none";

        if (emptyMessage) {
            emptyMessage.textContent =
                "No historical PM2.5 records are available for this city.";

            emptyMessage.classList.remove("hidden");
        }

        return;
    }

    canvas.style.display = "block";

    if (emptyMessage) {
        emptyMessage.classList.add("hidden");
    }

    const labels = validRecords.map(record => {
        return formatChartTimestamp(getTimestamp(record));
    });

    const values = validRecords.map(record => {
        return Number(getPm25(record));
    });

    console.log(
        `AirVision chart: plotting ${values.length} historical records.`,
        values
    );

    pm25Chart = new Chart(canvas, {
        type: "line",

        data: {
            labels: labels,

            datasets: [
                {
                    label: "PM2.5 (µg/m³)",

                    data: values,

                    borderColor: "#3878f6",

                    backgroundColor: "rgba(56, 120, 246, 0.12)",

                    borderWidth: 2.5,

                    fill: true,

                    tension: 0.3,

                    pointRadius: values.length > 40 ? 2 : 3,

                    pointHoverRadius: 6,

                    pointHitRadius: 10,

                    spanGaps: false
                }
            ]
        },

        options: {
            responsive: true,

            maintainAspectRatio: false,

            animation: {
                duration: 500
            },

            interaction: {
                intersect: false,
                mode: "index"
            },

            plugins: {
                legend: {
                    display: true,
                    position: "top"
                },

                tooltip: {
                    callbacks: {
                        label: function(context) {
                            return (
                                `PM2.5: ${context.parsed.y} µg/m³`
                            );
                        }
                    }
                }
            },

            scales: {
                x: {
                    title: {
                        display: true,
                        text: "Observation time"
                    },

                    ticks: {
                        maxTicksLimit: 8,
                        maxRotation: 0,
                        autoSkip: true
                    },

                    grid: {
                        display: false
                    }
                },

                y: {
                    beginAtZero: true,

                    title: {
                        display: true,
                        text: "PM2.5 (µg/m³)"
                    }
                }
            }
        }
    });
}


/* =========================================================
   13. LOAD PM2.5 PREDICTION
========================================================= */

async function loadPrediction(city) {
    const cityName = getCityName(city);

    const errorBox = getElement("prediction-error");

    if (errorBox) {
        errorBox.textContent = "";
        errorBox.classList.add("hidden");
    }

    try {
        const path =
            `/api/predictions?city=${encodeURIComponent(cityName)}`;

        const data = await apiRequest(path);

        console.log(
            "AirVision prediction API response:",
            data
        );

        // Current trained model API response:
        //
        // {
        //   "latest_pm25": 85.2,
        //   "estimated_next_pm25": 95.35,
        //   "metrics": {
        //     "mae": 6.53,
        //     "rmse": 9.46,
        //     "r2": 0.90
        //   }
        // }

        const latestRaw = getField(data, [
            "latest_pm25",
            "latest_pm2_5",
            "current_pm25"
        ]);

        const predictedRaw = getField(data, [
            "estimated_next_pm25",
            "predicted_pm25",
            "predicted_pm2_5",
            "prediction"
        ]);

        const latest = Number(latestRaw);
        const predicted = Number(predictedRaw);

        if (
            latestRaw === null ||
            predictedRaw === null ||
            !Number.isFinite(latest) ||
            !Number.isFinite(predicted)
        ) {
            throw new Error(
                "The prediction API did not return valid PM2.5 values."
            );
        }

        const change = predicted - latest;

        setText(
            "forecast-latest",
            latest.toFixed(2)
        );

        setText(
            "forecast-predicted",
            predicted.toFixed(2)
        );

        setText(
            "forecast-change",
            `${change > 0 ? "+" : ""}${change.toFixed(2)}`
        );

        setText(
            "forecast-change-note",
            change > 0
                ? "Predicted increase"
                : change < 0
                    ? "Predicted decrease"
                    : "No predicted change"
        );

        const issueTime = getField(data, [
            "issue_time",
            "forecast_from",
            "measured_at"
        ]);

        const forecastTime = getField(data, [
            "forecast_for",
            "predicted_at",
            "target_timestamp"
        ]);

        if (issueTime && forecastTime) {
            setText(
                "forecast-time",
                `Input: ${formatTimestamp(issueTime)} · ` +
                `Forecast: ${formatTimestamp(forecastTime)}`
            );
        } else {
            setText(
                "forecast-time",
                "Forecast horizon: approximately 1 hour"
            );
        }

        setText(
            "prediction-status",
            data.note ||
            "Experimental PM2.5 estimate. Not an official air-quality reading or health advisory."
        );

        // Update the prediction chart.

        updateForecastChart(
            cityName,
            latest,
            predicted
        );

        // Read model metrics.

        const metrics =
            data.metrics ||
            data.model_metrics ||
            {};

        if (metrics.mae !== null && metrics.mae !== undefined) {
            setText(
                "model-mae",
                displayValue(metrics.mae)
            );
        }

        if (metrics.rmse !== null && metrics.rmse !== undefined) {
            setText(
                "model-rmse",
                displayValue(metrics.rmse)
            );
        }

        if (metrics.r2 !== null && metrics.r2 !== undefined) {
            const r2 = Number(metrics.r2);

            setText(
                "model-r2",
                Number.isFinite(r2) ? r2.toFixed(3) : "--"
            );
        }

        const testRows =
            metrics.testing_rows ??
            metrics.test_rows;

        if (testRows !== null && testRows !== undefined) {
            setText(
                "model-test-rows",
                testRows
            );
        }

        console.log(
            "AirVision prediction values:",
            {
                city: cityName,
                latest,
                predicted,
                change,
                metrics
            }
        );

    } catch (error) {
        console.error(
            "AirVision prediction request failed:",
            error
        );

        if (errorBox) {
            errorBox.textContent =
                `Prediction unavailable for ${cityName}: ${error.message}`;

            errorBox.classList.remove("hidden");
        }

        setText(
            "prediction-status",
            "Check the prediction API and saved model."
        );

        // Do not destroy the historical chart if prediction fails.
    }
}


/* =========================================================
   14. RENDER PREDICTION COMPARISON CHART
========================================================= */

function updateForecastChart(cityName, latest, predicted) {
    const canvas = getElement("forecast-chart");

    if (!canvas) {
        console.warn(
            'Canvas with ID "forecast-chart" was not found.'
        );

        return;
    }

    if (typeof Chart === "undefined") {
        console.error(
            "Chart.js is unavailable."
        );

        return;
    }

    const chartData = {
        labels: [
            "Latest PM2.5",
            "Predicted PM2.5"
        ],

        datasets: [
            {
                label: `${cityName} PM2.5 (µg/m³)`,

                data: [
                    latest,
                    predicted
                ],

                backgroundColor: [
                    "rgba(56, 120, 246, 0.35)",
                    "rgba(22, 199, 132, 0.35)"
                ],

                borderColor: [
                    "#3878f6",
                    "#16a085"
                ],

                borderWidth: 2,

                borderRadius: 7
            }
        ]
    };

    if (forecastChart) {
        forecastChart.data = chartData;
        forecastChart.update();
        return;
    }

    forecastChart = new Chart(canvas, {
        type: "bar",

        data: chartData,

        options: {
            responsive: true,

            maintainAspectRatio: false,

            plugins: {
                legend: {
                    display: false
                },

                tooltip: {
                    callbacks: {
                        label: function(context) {
                            return (
                                `${context.parsed.y} µg/m³`
                            );
                        }
                    }
                }
            },

            scales: {
                y: {
                    beginAtZero: true,

                    title: {
                        display: true,
                        text: "PM2.5 (µg/m³)"
                    }
                },

                x: {
                    grid: {
                        display: false
                    }
                }
            }
        }
    });
}


/* =========================================================
   15. RESET DASHBOARD VALUES
========================================================= */

function resetDashboardValues() {
    // Air quality.

    setText("pm25-value", "--");
    setText("pm10-value", "--");

    // Weather.

    setText("temperature-value", "--");
    setText("humidity-value", "--");

    setText("weather-temperature", "--");
    setText("weather-humidity", "--");
    setText("weather-wind", "--");
    setText("weather-time", "--");

    // Predictions.

    setText("forecast-latest", "--");
    setText("forecast-predicted", "--");
    setText("forecast-change", "--");
    setText("forecast-change-note", "Loading prediction...");
    setText("forecast-time", "--");

    setText("prediction-status", "Loading prediction...");

    // Chart subtitle.

    const select = getElement("city-select");

    if (select && select.selectedOptions.length > 0) {
        setText(
            "chart-subtitle",
            `${select.selectedOptions[0].textContent} · Historical observations`
        );
    }
}


/* =========================================================
   16. LOAD DATA FOR THE SELECTED CITY
========================================================= */

async function loadSelectedCity() {
    const requestId = ++currentRequestId;

    clearError();

    const select = getElement("city-select");

    if (!select) {
        showError(
            'The city selector with ID "city-select" was not found.'
        );

        return;
    }

    const selectedValue = select.value;

    const city = cities.find(item => {
        return (
            String(getCityId(item) ?? getCityName(item)) ===
            selectedValue
        );
    });

    if (!city) {
        showError(
            "Please select a valid city."
        );

        return;
    }

    const cityName = getCityName(city);

    console.log(
        "AirVision selected city:",
        cityName
    );

    resetDashboardValues();

    // Hide the previous chart while the new city loads.

    const emptyMessage = getElement("chart-empty");

    if (emptyMessage) {
        emptyMessage.classList.add("hidden");
    }

    try {
        // Load air-quality history and weather in parallel.

        const results = await Promise.allSettled([
            loadAirQuality(city),
            loadWeather(city)
        ]);

        // Ignore responses from an older city selection.

        if (requestId !== currentRequestId) {
            console.log(
                "AirVision: ignored outdated city response."
            );

            return;
        }

        const airResult = results[0];
        const weatherResult = results[1];

        // Update historical air-quality data.

        if (airResult.status === "fulfilled") {
            updateAirQualityMetrics(airResult.value);
        } else {
            console.error(
                "Historical air-quality request failed:",
                airResult.reason
            );

            updateAirQualityMetrics([]);

            showError(
                `Could not load historical air-quality data for ${cityName}: ` +
                `${airResult.reason?.message || "Unknown error"}`
            );
        }

        // Update weather information.

        if (weatherResult.status === "fulfilled") {
            updateWeatherMetrics(weatherResult.value);
        } else {
            console.error(
                "Weather request failed:",
                weatherResult.reason
            );

            updateWeatherMetrics([]);

            showError(
                `Could not load weather data for ${cityName}: ` +
                `${weatherResult.reason?.message || "Unknown error"}`
            );
        }

        // Load the one-hour prediction.

        await loadPrediction(city);

        if (requestId !== currentRequestId) {
            return;
        }

        // Update refresh timestamp.

        setText(
            "last-updated",
            `Last refreshed: ${new Date().toLocaleTimeString()}`
        );

        console.log(
            `AirVision dashboard loaded for ${cityName}.`
        );

    } catch (error) {
        console.error(
            "Failed to load selected city:",
            error
        );

        if (requestId === currentRequestId) {
            showError(
                `Unable to load dashboard data for ${cityName}: ${error.message}`
            );
        }
    }
}


/* =========================================================
   17. INITIALIZE DASHBOARD
========================================================= */

async function initializeDashboard() {
    const refreshButton = getElement("refresh-button");

    if (refreshButton) {
        refreshButton.disabled = true;
    }

    clearError();

    setText(
        "connection-status",
        "Connecting to API..."
    );

    try {
        // Verify the backend and database connection.

        const health = await apiRequest("/api/health");

        console.log(
            "AirVision health response:",
            health
        );

        if (health.database_status !== "connected") {
            throw new Error(
                "The API is running, but the database is not connected."
            );
        }

        setText(
            "connection-status",
            "API and database connected"
        );

        const statusDot = document.querySelector(".status-dot");

        if (statusDot) {
            statusDot.style.background = "#16c784";
        }

        // Load available cities.

        await loadCities();

        // Load the selected city's data.

        await loadSelectedCity();

    } catch (error) {
        console.error(
            "Dashboard initialization failed:",
            error
        );

        setText(
            "connection-status",
            "Connection failed"
        );

        const statusDot = document.querySelector(".status-dot");

        if (statusDot) {
            statusDot.style.background = "#ef4444";
        }

        showError(
            `Dashboard initialization failed: ${error.message}. ` +
            "Make sure FastAPI and PostgreSQL are running."
        );

    } finally {
        if (refreshButton) {
            refreshButton.disabled = false;
        }
    }
}


/* =========================================================
   18. EVENT LISTENERS
========================================================= */

// Change the city and reload its data.

document.addEventListener("DOMContentLoaded", () => {
    const citySelect = getElement("city-select");

    if (citySelect) {
        citySelect.addEventListener(
            "change",
            loadSelectedCity
        );
    }

    // Refresh button.

    const refreshButton = getElement("refresh-button");

    if (refreshButton) {
        refreshButton.addEventListener(
            "click",
            initializeDashboard
        );
    }

    console.log(
        "AirVision frontend JavaScript loaded successfully."
    );

    initializeDashboard();
});