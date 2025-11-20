#!/bin/bash

ESTRUCTURA="$1"

case $ESTRUCTURA in
    "SAVE_THE_CAT")
        echo "prompts/02_save_the_cat.txt"
        ;;
    "HERO_JOURNEY")
        echo "prompts/02_hero_journey.txt"
        ;;
    "STORY_CIRCLE")
        echo "prompts/02_story_circle.txt"
        ;;
    "THREE_ACT")
        echo "prompts/02_arquitecto.txt"
        ;;
    "FIVE_ACT")
        echo "prompts/02_five_act.txt"
        ;;
    "IN_MEDIA_RES")
        echo "prompts/02_in_media_res.txt"
        ;;
    "SIMPLE")
        echo "prompts/02_simple.txt"
        ;;
    *)
        echo "prompts/02_arquitecto.txt"
        ;;
esac
