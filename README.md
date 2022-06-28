# MESsy

Minimalistic MES for University project. Optimized for specific usecase of a tiny productionline of a sewing company.

# Usage

## Requirements

- Python Version at least 3.10

## Setup

1. Create and activate a python virtual environment (Example is for Linux)

        python3.10 -m venv .venv
        source .venv/bin/activate

2. Install all pip requrements:

        pip install -r requirements.txt

3. Init the DB:

        python init_db.py

4. start the Server:

        uvicorn MESsy:app --host 0.0.0.0 --port 8000 --log-level critical --workers 4

# API

Ressource|GET|POST|PUT|DELETE
-|-|-|-|-
/MESsy/logininfo|Login-Infos|||
/MESsy/\<id\>/login||Login||Logout
/MESsy/\<id\>/help|Get help message|||
/MESsy/\<id\>/job|Get current Job|Job Done||
/MESsy/\<id\>/cancel_job||Cancle Job||
/MESsy/\<id\>/error||Send Error-Message||
/MESsy/\<id\>/stats|Get statistics|||

## Remarks

\<id\> should be the Serialnumber of the Machine  
Data is send in JSON format

## Example values

### MESsy/\<id\>/job GET

    { 
        "Materialnumber":1, 
        "Product_Name":"Jacket", 
        "Quantity":2, 
        "Description":"Jacket you can wear", 
        "URL_Pictures":[
        ], 
        "URL_Videos":[ 
        ], 
        "Split":0, 
        "Steps":[ 
            { 
                "Job":1, 
                "Step_Number":1, 
                "Specified_Time":2.34, 
                "Additional_Informations":"", 
                "Step_Description":"Sew" 
            }, 
            { 
                "Job":2, 
                "Step_Number":2, 
                "Specified_Time":0, 
                "Additional_Informations":"", 
                "Step_Description":"Cut" 
            }, 
        ] 
    }

### MESsy/\<id\>/cancel_job POST

    { 
        "Produced":0 
    } 

### MESsy/\<id\>/error POST 

    { 
        "Message":"string", 
        "Interrupted":true, 
        "Produced":0 
    } 

### MESsy/logininfo GET

    { 
        "Rooms":[ 
            { 
                "id":1, 
                "room":"205-123" 
            }, 
            { 
                "id":2, 
                "room":"210-003" 
            } 
        ], 
        "Users":[ 
            { 
                "id":1, 
                "user":"Max" 
            }, 
            { 
                "id":2, 
                "user":"John" 
            }, 
            { 
                "id":3, 
                "user":"Tom" 
            } 
        ], 
        "Serialnumbers":[ 
            123, 
            321, 
            456 
        ] 
    } 

### MESsy/\<id\>/stats GET

    {
        "ratio_done":0.123
    } 

# Links

Admin Page: \<IP\>:8000/ui/HTML/admin.html

# Further Information

In case of questions or problems just open a Issue.