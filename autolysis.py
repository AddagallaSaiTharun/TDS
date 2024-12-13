# /// script
# requires-python = ">3.12"
# dependencies = [
#     'requests<3' ,
#     'python-dotenv',
#     'pandas',
#     'numpy',
#     'seaborn',
#     'matplotlib',
#     'scipy',
#     'chardet',
#     'python-dotenv'
# ]
# ///

import pandas as pd
import requests
from dotenv import load_dotenv
import os
import json
import sys
import traceback
import chardet
import base64
import concurrent.futures
import time


start = time.time()
print("started: ")
# Load environment variables
# load_dotenv()
# finally
AIPROXY_TOKEN = os.environ.get('AIPROXY_TOKEN')

URL = os.environ.get('URL_OPENAI',"http://aiproxy.sanand.workers.dev/openai/v1/chat/completions")
MODEL = "gpt-4o-mini"
HEADERS = {
    "Content-Type": "application/json",
    "Authorization": f"Bearer {AIPROXY_TOKEN}"
}

def request_llm(functions, user_content, sys_content, name, code=None, error=None):
    """Make a request to the LLM with optional code and error context."""
    if code and error:
        user_content = f"{code}\n{error}"
    data = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": sys_content},
            {"role": "user", "content": user_content}
        ],
        "functions": functions,
        "function_call": {"name": name},
    }
    response = requests.post(URL, headers=HEADERS, json=data, timeout=120)
    return json.loads(response.json()["choices"][0]["message"]["function_call"]["arguments"])

def execute_llm(functions, user_content, sys_content, name):
    """Attempt to execute LLM-generated Python code up to 3 times."""
    code_list, error_list = [], []
    for _ in range(3):
        try:
            res = request_llm(functions, user_content, sys_content, name, 
                              code_list[-1] if code_list else None, 
                              error_list[-1] if error_list else None)
            code = res.get('python_code', '')
            code_list.append(code)
            exec(code)
            return False, code_list, res  # Execution succeeded
        except Exception as e:
            error = traceback.format_exc().splitlines()[-1]
            error_list.append(error)
    return True, error_list, None  # Execution failed after retries

FUNCTIONS = [
    {
        "name": "get_column_type",
        "description": "Identify column names and their data types from a dataset.",
        "parameters": {
            "type": "object",
            "properties": {
                "column_metadata": {
                    "type": "array",
                    "description": "Metadata for each object",
                    "items": {
                        "type": "object",
                        "properties": {
                            "column_name": {"type": "string", "description": "Name of the column"},
                            "column_type": {"type": "string", "description": "Data type of the column (e.g., integer, string)"}
                        },
                        "required": ["column_name", "column_type"]
                    },
                    "minItems": 1
                }
            },
            "required": ["column_metadata"]
        }
    },
    {
        "name": "get_correlation_plot",
        "description": "Generate Python code to compute a correlation matrix, find highest correlated columns, and create a scatterplot.",
        "parameters": {
            "type": "object",
            "properties": {
                "python_code": {"type": "string", "description": "Python code to generate correlation matrix and scatterplot."}
            },
            "required": ["python_code"]
        }
    },
    {
        "name": "replace_null_values",
        "description": "Generate Python code to replace null values in columns with specified methods.",
        "parameters": {
            "type": "object",
            "properties": {
                "python_code": {"type": "string", "description": "Python code to replace null values."},
                "null_cols": {
                    "type": "array",
                    "description": "Column names and replacement strategies.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "column_name": {"type": "string", "description": "Name of the column."},
                            "replace_with": {"type": "string", "description": "Replacement method (mean, median, etc.)."},
                            "reason": {"type": "string", "description": "Reason for chosen replacement method."}
                        },
                        "required": ["column_name", "replace_with", "reason"]
                    }
                }
            },
            "required": ["python_code", "null_cols"]
        }
    },
    {
        "name": "generate_chart_binnable",
        "description": "Identify binnable columns and generate subplot chart as PNG.",
        "parameters": {
            "type": "object",
            "properties": {
                "python_code": {"type": "string", "description": "Python code for creating subplot."},
                "chart_name": {"type": "string", "description": "Name of the PNG file."},
                "binnable_cols": {
                    "type": "array",
                    "description": "Columns marked as binnable or not with reasons.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "column_name": {"type": "string", "description": "Name of the column."},
                            "is_binnable": {"type": "boolean", "description": "True if binnable, False otherwise."},
                            "reason": {"type": "string", "description": "Reason for binning decision."}
                        },
                        "required": ["column_name", "is_binnable", "reason"]
                    }
                }
            },
            "required": ["python_code", "chart_name", "binnable_cols"]
        }
    },
    {
        "name": "analyze_chart",
        "parameters": {
            "type": "object",
            "properties": {
                "metadata": {"type": "string", "description": "Chart description or context."},
                "extracted_insights": {"type": "string", "description": "Insights from the chart."}
            },
            "required": ["metadata", "extracted_insights"]
        }
    },
    {
        "name": "readME_md_creator",
        "parameters": {
            "type": "object",
            "properties": {
                "readme_content": {"type": "string", "description": "Structured README.md content."}
            }
        }
    },
    {
        "name": "outlier_detection",
        "description": "Detect outliers in the dataset and create a box plot.",
        "parameters": {
            "type": "object",
            "properties": {
                "python_code": {"type": "string", "description": "Python code to identify outliers using IQR method."}
            },
            "required": ["python_code"]
        }
    },
    {
        "name": "skew_category",
        "description": "Categorize columns based on skewness.",
        "parameters": {
            "type": "object",
            "properties": {
                "left_skewed": {
                    "type": "array", "description": "Left-skewed columns.", "items": {"type": "string"}
                },
                "right_skewed": {
                    "type": "array", "description": "Right-skewed columns.", "items": {"type": "string"}
                },
                "normally_distributed": {
                    "type": "array", "description": "Normally distributed columns.", "items": {"type": "string"}
                }
            },
            "required": ["left_skewed", "right_skewed", "normally_distributed"]
        }
    }
]

# Load Dataset
file_path = sys.argv[1]
file_folder = file_path.split(".csv")[0].split('\\')[-1]
os.makedirs(file_folder, exist_ok=True)
readME = {}

# Detect Encoding
with open(file_path, "rb") as f:
    encoding = chardet.detect(f.read())['encoding']

with open(file_path, "r", encoding=encoding) as f:
    data = ''.join([f.readline() for _ in range(5)])

df = pd.read_csv(file_path, encoding=encoding)

# Metadata Analysis
SYS_CONTENT = (
    "Analyse the dataset with the first line as the header and subsequent lines as samples. "
    "Ignore unclean cells and infer data types based on majority values. "
    "Supported types: 'str', 'int', 'datetime', 'boolean', 'float'."
)

USER_CONTENT = f"Dataset sample:\n{data}"

metadata = request_llm(FUNCTIONS, USER_CONTENT, SYS_CONTENT, "get_column_type")['column_metadata']

# Update DataFrame Columns
for column in metadata:
    col_name, col_type = column['column_name'], column['column_type']

    if col_type in {'int', 'float'} and df[col_name].dtype == 'object':
        df[col_name] = pd.to_numeric(df[col_name], errors='coerce')
    elif col_type == 'datetime' and df[col_name].dtype == 'object':
        df[col_name] = pd.to_datetime(df[col_name], errors='coerce')
    elif col_type == 'boolean' and df[col_name].dtype == 'object':
        df[col_name] = df[col_name].astype(bool)
    elif col_type == 'str' and df[col_name].dtype in {'float64', 'int64'}:
        column['column_type'] = 'float' if 'float' in str(df[col_name].dtype) else 'int'

# BASIC INSIGHTS OF THE DATASET
readME['basic'] = {
    'num_rows': df.shape[0],
    'num_columns': df.shape[1],
    'column': list(df.columns),
    'sample_data': data,
    'missing_values': df.isnull().sum().to_dict(),
    'col_type': metadata
}

print("Metadata:",time.time() - start)
# DATASET PREPROCESSING 
null_details = {col: count for col, count in df.isnull().sum().items() if count > 0}
null_columns = {col: json.loads(df[col].describe().to_json()) for col in null_details}

SYS_CONTENT = (
    "The data provided consists of only those column names which contain null/nan values and the corresponding statistics of those columns.\n"
    "Figure out from the statistics with what to replace the null/nan values. Is it with either `mean` or `median` or `most frequent` or some `constant value`.\n"
    "In case you cannot decide what to fill null values with, fill them with `Unknown`.\n"
    "Generate python code to replace null/nan in the columns provide with either `mean` or `median` or `most frequent` or some `constant value`.\n"
    "Do not add comments to the code.\n"
    "Do not make your own data, dataset is stored in the dataframe named ```df``` ."
)

USER_CONTENT = f"{null_columns}"
isError, code_list, res = execute_llm(FUNCTIONS, USER_CONTENT, SYS_CONTENT, 'replace_null_values')
if not isError:
    readME['preprocessing'] = res['null_cols']

print("Preprocessing:",time.time() - start)
# GRAPH FOR BINNABLE COLUMNS
numeric_columns = [
    {col['column_name']: json.loads(df.describe()[col['column_name']].to_json())}
    for col in metadata if col['column_type'] in {'int', 'float'}
]

SYS_CONTENT = (
    "The data provided consists of column names which are numeric and the statistics related to those columns.\n"
    "From these statistics decide which columns are binnable and which are not.\n"
    "Separate those columns which are binnable and which are not binnable along with a reason.\n"
    "Consider those columns which are binnable and generate a subplot of graphs for each of the column which is binnable.\n"
    "Each graph in the subplot should be chosen such that it showcases the binnable property of a column.\n"
    "Get the column names from the data provided.\n"
    "Generate python code to create a subplot of graphs.\n"
    "Make use of modules like matplotlib and seaborn if needed.\n"
    "Do not add any comments to python code.\n"
    "Do not make your own data, the dataset is stored in dataframe named ```df``` .\n"
    f"Export/save the chart/subplot as png file and don't show the chart. Save the chart in {file_folder} folder."
)

USER_CONTENT = f"{numeric_columns}"
isError, code_list, res = execute_llm(FUNCTIONS, USER_CONTENT, SYS_CONTENT, 'generate_chart_binnable')
readME['binnable_cols_reasons'] = res['binnable_cols']
CHART_BINNABLE = res['chart_name']
print("binnable:",time.time() - start)

# OUTLIER DETECTION
readME['outliers'] = [
    {
        "column": col,
        "outlier_count": len(df[(df[col] < (lb := Q1 - 1.5 * (Q3 - Q1))) | (df[col] > (ub := Q3 + 1.5 * (Q3 - Q1)))]),
        "lower_bound": lb,
        "upper_bound": ub
    }
    for col in df.select_dtypes(include=['number']).columns
    for Q1, Q3 in [(df[col].quantile(0.25), df[col].quantile(0.75))]
]

# Load and preprocess image for analysis
def encode_image(filePath):
    with open(filePath, "rb") as fl:
        return base64.b64encode(fl.read()).decode("utf-8")

# Analyze skewness from binnable chart
image_path = f"{file_folder}/{CHART_BINNABLE}"
base64_image = encode_image(image_path)

SYS_CONTENT = """
Analyse the given chart containing histograms of columns to determine skewness.
Categorize columns as `Right Skewed`, `Left Skewed`, or `Normally Distributed`.
"""

USER_CONTENT = [
    {"type": "text", "text": "Analyse this image."},
    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{base64_image}", "detail": "low"}},
]

resp = request_llm(FUNCTIONS, USER_CONTENT, SYS_CONTENT, 'skew_category')
readME['skewed'] = {
    'left_skewed': resp['left_skewed'],
    'right_skewed': resp['right_skewed'],
    'normally_distributed': resp['normally_distributed']
}

print("skwed:",time.time() - start)
# Correlation matrix and scatter plot generation
SYS_CONTENT = f"""
Generate a correlation matrix for the dataset `df` and identify the pair of columns with the highest correlation (excluding 1.0).
Create a scatter plot for the identified pair and save the correlation matrix heatmap and scatter plot as PNG files in {file_folder}/.
"""

USER_CONTENT = """
Generate a correlation matrix, find the highest correlated columns, and create a scatter plot.
Exclude non-numeric columns using `numeric_only`.
"""

isError, code_list, res = execute_llm(FUNCTIONS, USER_CONTENT, SYS_CONTENT, "get_correlation_plot")
print("corelatioina and scatter plot:",time.time() - start)

# Analyze and extract insights from generated charts
# visualization_data = []
# for file in os.listdir(file_folder):
#     if file.endswith(".png"):
#         base64_image = encode_image(os.path.join(file_folder, file))

#         SYS_CONTENT = """
#         Analyze the provided chart to extract insights.
#         Provide a brief description and key insights derived from the chart.
#         """

#         USER_CONTENT = [
#             {"type": "text", "text": "Analyze the chart."},
#             {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{base64_image}", "detail": "low"}},
#         ]

#         res = request_llm(FUNCTIONS, USER_CONTENT, SYS_CONTENT, "analyze_chart")
#         insights, metadata = res['extracted_insights'], res['metadata']
#         visualization_data.append({
#             "insights": insights,
#             "metadata": metadata,
#             "file_path": file
#         })

# readME['insights'] = visualization_data

# Function to encode image to base64

# Function to process the chart and get insights
def process_image(file_path):
    base64_image = encode_image(file_path)

    SYS_CONTENT = """
    Analyze the provided chart to extract insights.
    Provide a brief description and key insights derived from the chart.
    """
    
    USER_CONTENT = [
        {"type": "text", "text": "Analyze the chart."},
        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{base64_image}", "detail": "low"}},
    ]
    
    # Request insights from LLM (mocked function in this case)
    res = request_llm(FUNCTIONS, USER_CONTENT, SYS_CONTENT, "analyze_chart")
    insights, metadata = res['extracted_insights'], res['metadata']
    
    return {
        "insights": insights,
        "metadata": metadata,
        "file_path": file_path
    }

# List to store visualization data
visualization_data = []

# Function to process all images using multithreading
def process_all_images(file_folder):
    with concurrent.futures.ThreadPoolExecutor() as executor:
        # Create a list of file paths for all .png images
        files = [os.path.join(file_folder, file) for file in os.listdir(file_folder) if file.endswith(".png")]

        # Use map to process images in parallel
        for result in executor.map(process_image, files):
            visualization_data.append(result)

    # Assuming you want to store the results in a dictionary
    readME['insights'] = visualization_data

# Run the function to process all images
process_all_images(file_folder)
print("Images vis:",time.time() - start)
# Formatted markdown content for README.md
readme_content = f"""
# Analysis Report for `{file_folder}`

## Dataset Overview
- **Number of Rows**: {readME['basic'].get('num_rows', 'N/A')}
- **Number of Columns**: {readME['basic'].get('num_columns', 'N/A')}
- **Columns**:\n {readME['basic']['column']} \n\n
- **Data Types**:\n{readME['basic']['col_type']}\n\n

## Sample Data
{readME['basic'].get('sample_data', 'No sample data available')}\n\n

## Key Insights from Analysis
### Basic Analysis
- **Missing Values**:\n{readME['basic']['missing_values']}\n\n
## Preprocessing Insights
- **Imputing Missing Values and Reasoning**:\n{readME['preprocessing']}\n\n

## Binnable Columns Insights
- **Binnable Columns and Reasoning**:\n{readME['binnable_cols_reasons']}\n\n

## Visualizations and Insights
{"".join([f"![{os.path.basename(entry['file_path'])}]({entry['file_path']})\n- **Chart Description**: {entry['metadata']}\n- **LLM Analysis**: {entry['insights']}\n\n" for entry in readME['insights']])}

- **Outliers**:\n{"\n".join([f"  - Column `{outlier['column']}`: {outlier['outlier_count']} outliers detected (Range: {outlier['lower_bound']} to {outlier['upper_bound']})" for outlier in readME['outliers']])}

## Recommendations and Next Steps
- **Data Quality**: Address missing values and outliers for cleaner analysis.
- **Future Exploration**: Use clustering and PCA insights for segmentation and dimensionality reduction.
- **Operational Use**: Leverage time-series patterns for forecasting and geospatial trends for targeted decision-making.

## MIT License
Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files, to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

- The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.
- The software is provided "as is", without warranty of any kind, express or implied, including but not limited to the warranties of merchantability, fitness for a particular purpose and noninfringement. In no event shall the authors or copyright holders be liable for any claim, damages or other liability, whether in an action of contract, tort or otherwise, arising from, out of or in connection with the software or the use or other dealings in the software.
"""

SYS_CONTENT = """
Refine the markdown content to create a well-structured README.md file.  
The README should include headers, lists, and emphasis to clearly describe the data, analysis performed, insights gained, and implications.  
Use the provided markdown content as a base and improve its structure, clarity, and overall presentation.  
Ensure the final README is concise, informative, and easy to understand.
"""
USER_CONTENT = f"""
Add MIT license to the markdown.
The markdown to be refined is:
{readme_content}
""" 
res = request_llm(FUNCTIONS,USER_CONTENT,SYS_CONTENT,"readME_md_creator")
readME = res['readme_content']
# Write the formatted content to README.md file
file_folder_path = f"{file_folder}/README.md"
with open(file_folder_path, "w", encoding="utf-8") as f:
    f.write(readME)

end = time.time()

print("end time: ",(end-start))
